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
    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        self.client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)

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
    async def complete(self, **kwargs):
        raise RuntimeError("OPENAI_API_KEY is not configured")
