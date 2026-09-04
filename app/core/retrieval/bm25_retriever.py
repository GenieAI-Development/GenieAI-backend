from __future__ import annotations

from app.indexing.bm25_indexer import BM25Indexer
from app.repositories.catalogue_repository import CatalogueRepository
from app.schemas.internal import RetrievalPlan


class BM25Retriever:
    def __init__(
        self, indexer: BM25Indexer, repository: CatalogueRepository, top_k: int = 40
    ) -> None:
        self.indexer = indexer
        self.repository = repository
        self.top_k = top_k

    async def retrieve(self, plan: RetrievalPlan) -> list[tuple[str, float]]:
        raw = self.indexer.search(
            plan.category, plan.query, max(self.top_k, plan.candidate_limit)
        )
        products = {
            item.product_id: item for item in self.repository.load_category(plan.category).products
        }
        excluded_ids = set(plan.stable_filters.excluded_product_ids)
        excluded_vendors = {value.casefold() for value in plan.stable_filters.excluded_vendors}
        vendor = plan.stable_filters.vendor.casefold() if plan.stable_filters.vendor else None
        filtered = []
        for product_id, score in raw:
            product = products.get(product_id)
            if product is None or not product.is_active or product_id in excluded_ids:
                continue
            if vendor and product.vendor.casefold() != vendor:
                continue
            if product.vendor.casefold() in excluded_vendors:
                continue
            if (
                plan.stable_filters.exact_weight_kg is not None
                and product.weight_kg != plan.stable_filters.exact_weight_kg
            ):
                continue
            filtered.append((product_id, score))
        return filtered

