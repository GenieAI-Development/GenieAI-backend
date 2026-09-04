from __future__ import annotations

import hashlib
from typing import Protocol, Sequence

from openai import AsyncOpenAI

from app.schemas.catalogue import CatalogueProduct


def build_dense_text(product: CatalogueProduct) -> str:
    if product.visual_interpretation:
        return f"{product.description}\n\n{product.visual_interpretation}"
    return product.description


def dense_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingClient(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAIEmbeddingClient:
    def __init__(
        self, api_key: str, model: str, dimension: int, timeout_seconds: float = 30.0
    ) -> None:
        self.client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=2)
        self.model = model
        self.dimension = dimension

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model=self.model, input=list(texts), dimensions=self.dimension
        )
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]


class UnavailableEmbeddingClient:
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise RuntimeError("OPENAI_API_KEY is not configured")
