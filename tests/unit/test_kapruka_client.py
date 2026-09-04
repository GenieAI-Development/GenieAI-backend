from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.integrations.kapruka.client import McpKaprukaClient


def _wrapped_result(payload: dict):
    return SimpleNamespace(
        isError=False,
        structuredContent={"result": json.dumps(payload)},
        content=[],
    )


@pytest.mark.asyncio
async def test_get_product_uses_kapruka_params_and_unwraps_json_result():
    client = McpKaprukaClient(url="https://mcp.example.test/mcp")
    client._call_once = AsyncMock(  # type: ignore[method-assign]
        return_value=_wrapped_result({"id": "P1", "in_stock": True})
    )

    result = await client.get_product("P1")

    assert result == {"id": "P1", "in_stock": True}
    client._call_once.assert_awaited_once_with(  # type: ignore[attr-defined]
        "kapruka_get_product",
        {
            "params": {
                "product_id": "P1",
                "currency": "LKR",
                "response_format": "json",
            }
        },
    )


@pytest.mark.asyncio
async def test_delivery_uses_check_tool_and_reads_available():
    client = McpKaprukaClient(url="https://mcp.example.test/mcp")
    client._call_once = AsyncMock(  # type: ignore[method-assign]
        return_value=_wrapped_result({"available": True})
    )

    assert await client.validate_delivery("Colombo 03", "2026-09-05") is True
    client._call_once.assert_awaited_once_with(  # type: ignore[attr-defined]
        "kapruka_check_delivery",
        {
            "params": {
                "city": "Colombo 03",
                "delivery_date": "2026-09-05",
                "response_format": "json",
            }
        },
    )
