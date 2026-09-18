from __future__ import annotations

from typing import Protocol, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel


OutputT = TypeVar("OutputT", bound=BaseModel)


class StructuredLLMClient(Protocol):
    async def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[OutputT],
    ) -> OutputT: ...


class OpenAIStructuredLLMClient:
    def __init__(
        self,
        api_key: str,
        timeout_seconds: float = 30.0,
        base_url: str | None = None,
    ) -> None:
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )

    async def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[OutputT],
    ) -> OutputT:
        response = await self.client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_model,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("model returned no validated structured output")
        return parsed


class UnavailableLLMClient:
    def __init__(self, required_setting: str = "OPENAI_API_KEY") -> None:
        self.required_setting = required_setting

    async def complete(self, **kwargs):
        raise RuntimeError(f"{self.required_setting} is not configured")


class ModelRoutingLLMClient:
    """Routes explicitly configured models to a provider-specific client."""

    def __init__(
        self,
        routes: dict[str, StructuredLLMClient],
        default_client: StructuredLLMClient,
    ) -> None:
        self.routes = routes
        self.default_client = default_client

    async def complete(self, **kwargs):
        client = self.routes.get(kwargs["model"], self.default_client)
        return await client.complete(**kwargs)
