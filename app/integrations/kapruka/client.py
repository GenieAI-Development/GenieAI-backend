from __future__ import annotations

import asyncio
import json
from collections import deque
from contextlib import AsyncExitStack, asynccontextmanager
from contextvars import ContextVar
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from app.observability.logging import log_event


class KaprukaError(RuntimeError):
    """The configured Kapruka MCP operation failed or returned invalid data."""


class KaprukaClient(Protocol):
    async def get_product(self, product_id: str) -> dict[str, Any]: ...

    async def validate_delivery(self, city: str, delivery_date: str) -> bool: ...


class McpKaprukaClient:
    """Kapruka MCP adapter with Streamable HTTP and optional stdio fallback."""

    def __init__(
        self,
        *,
        url: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        delivery_tool: str = "kapruka_check_delivery",
        timeout_seconds: float = 15.0,
        max_attempts: int = 2,
        rate_limit_per_minute: int = 50,
    ) -> None:
        self.url = url
        self.command = command
        self.args = args or []
        self.delivery_tool = delivery_tool
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.rate_limit_per_minute = max(1, rate_limit_per_minute)
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._connect_lock = asyncio.Lock()
        self._rate_lock = asyncio.Lock()
        self._request_times: deque[float] = deque()
        self._remote_session: ContextVar[ClientSession | None] = ContextVar(
            f"kapruka_remote_session_{id(self)}", default=None
        )

    async def _acquire_rate_slot(self, slots: int = 1) -> None:
        slots = max(1, min(slots, self.rate_limit_per_minute))
        while True:
            async with self._rate_lock:
                now = asyncio.get_running_loop().time()
                cutoff = now - 60.0
                while self._request_times and self._request_times[0] <= cutoff:
                    self._request_times.popleft()
                if len(self._request_times) + slots <= self.rate_limit_per_minute:
                    self._request_times.extend(now for _ in range(slots))
                    return
                delay = max(0.01, 60.0 - (now - self._request_times[0]))
            await asyncio.sleep(delay)

    async def connect(self) -> ClientSession:
        if self.url:
            raise KaprukaError(
                "Streamable HTTP sessions are scoped to each call; connect() is stdio-only"
            )
        if self._session is not None:
            return self._session
        async with self._connect_lock:
            if self._session is not None:
                return self._session
            if not self.command:
                raise KaprukaError("KAPRUKA_MCP_COMMAND is not configured")
            stack = AsyncExitStack()
            try:
                parameters = StdioServerParameters(
                    command=self.command, args=self.args
                )
                read_stream, write_stream = await stack.enter_async_context(
                    stdio_client(parameters)
                )
                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                await session.initialize()
            except Exception:
                await stack.aclose()
                raise
            self._stack = stack
            self._session = session
            return session

    async def close(self) -> None:
        async with self._connect_lock:
            stack = self._stack
            self._stack = None
            self._session = None
            if stack is not None:
                await stack.aclose()

    @asynccontextmanager
    async def session_scope(self):
        """Reuse one remote session within a request-local operation batch."""
        if not self.url:
            await self.connect()
            yield
            return
        if self._remote_session.get() is not None:
            yield
            return
        async with streamablehttp_client(
            self.url,
            timeout=self.timeout_seconds,
            sse_read_timeout=max(self.timeout_seconds, 300.0),
            terminate_on_close=True,
        ) as streams:
            read_stream, write_stream = streams[0], streams[1]
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                token = self._remote_session.set(session)
                try:
                    yield
                finally:
                    self._remote_session.reset(token)

    async def _call_once(self, tool_name: str, arguments: dict[str, Any]):
        if self.url:
            session = self._remote_session.get()
            if session is not None:
                return await session.call_tool(tool_name, arguments=arguments)
            async with self.session_scope():
                session = self._remote_session.get()
                if session is None:
                    raise KaprukaError("Kapruka MCP session did not initialize")
                return await session.call_tool(tool_name, arguments=arguments)
        session = await self.connect()
        return await session.call_tool(tool_name, arguments=arguments)

    @staticmethod
    def _decode_object(value: object) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if not isinstance(value, str):
            return None
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    async def _call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        result = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                # Streamable HTTP tool calls can produce more than one HTTP request.
                # Reserve two slots and retain headroom for session setup/teardown.
                await self._acquire_rate_slot(2 if self.url else 1)
                async with asyncio.timeout(self.timeout_seconds):
                    result = await self._call_once(tool_name, arguments)
                break
            except Exception as exc:
                last_error = exc
                log_event(
                    "kapruka_mcp_attempt_failed",
                    tool=tool_name,
                    attempt=attempt,
                    failure_type=type(exc).__name__,
                )
        if result is None:
            raise KaprukaError(f"Kapruka MCP call failed: {tool_name}") from last_error
        if result.isError:
            raise KaprukaError(f"Kapruka MCP returned an error: {tool_name}")
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            decoded_result = self._decode_object(structured.get("result"))
            if decoded_result is not None:
                return decoded_result
            if "result" not in structured:
                return structured
        for content in result.content:
            text = getattr(content, "text", None)
            if not text:
                continue
            parsed = self._decode_object(text)
            if parsed is not None:
                return parsed
        raise KaprukaError(f"Kapruka MCP returned no structured object: {tool_name}")

    async def get_product(self, product_id: str) -> dict[str, Any]:
        return await self._call(
            "kapruka_get_product",
            {
                "params": {
                    "product_id": product_id,
                    "currency": "LKR",
                    "response_format": "json",
                }
            },
        )

    async def validate_delivery(self, city: str, delivery_date: str) -> bool:
        result = await self._call(
            self.delivery_tool,
            {
                "params": {
                    "city": city,
                    "delivery_date": delivery_date,
                    "response_format": "json",
                }
            },
        )
        available = result.get("available")
        if not isinstance(available, bool):
            raise KaprukaError("delivery response is missing boolean available")
        return available
