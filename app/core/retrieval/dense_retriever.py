from __future__ import annotations

from typing import Protocol, Sequence

from app.indexing.embedding_builder import EmbeddingClient
from app.schemas.internal import RetrievalPlan


class DenseSearchStore(Protocol):
    async def search(
        self,
        category: str,
        vector: Sequence[float],
        limit: int,
        vendor: str | None = None,
        excluded_vendors: set[str] | None = None,
        exact_weight_kg: float | None = None,
        excluded_product_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]: ...


class DenseRetriever:
    def __init__(self, store: DenseSearchStore, embeddings: EmbeddingClient, top_k: int = 40):
        self.store = store
        self.embeddings = embeddings
        self.top_k = top_k

    async def retrieve(self, plan: RetrievalPlan) -> list[tuple[str, float]]:
        vector = (await self.embeddings.embed([plan.query]))[0]
        return await self.store.search(
            plan.category,
            vector,
            max(self.top_k, plan.candidate_limit),
            vendor=plan.stable_filters.vendor,
            excluded_vendors=set(plan.stable_filters.excluded_vendors),
            exact_weight_kg=plan.stable_filters.exact_weight_kg,
            excluded_product_ids=set(plan.stable_filters.excluded_product_ids),
        )
