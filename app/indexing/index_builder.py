from __future__ import annotations

from app.indexing.bm25_indexer import BM25Indexer
from app.indexing.qdrant_indexer import QdrantIndexer
from app.repositories.catalogue_repository import CatalogueRepository
from app.schemas.admin import CatalogueHealthResponse, IndexBuildResponse


class IndexBuilder:
    def __init__(
        self,
        repository: CatalogueRepository,
        qdrant: QdrantIndexer,
        bm25: BM25Indexer,
    ) -> None:
        self.repository = repository
        self.qdrant = qdrant
        self.bm25 = bm25

    async def build(self, category: str, rebuild: bool = False) -> IndexBuildResponse:
        catalogue = self.repository.load_category(category)
        dense = await self.qdrant.build(catalogue, rebuild=rebuild)
        bm25_count = self.bm25.build(catalogue)
        health = await self.health(category)
        return IndexBuildResponse(
            category=category,
            dense_upserted=dense.upserted,
            dense_skipped=dense.skipped,
            dense_removed=dense.removed,
            bm25_documents=bm25_count,
            ready=health.ready,
        )

    async def health(self, category: str) -> CatalogueHealthResponse:
        catalogue = self.repository.load_category(category)
        active = {product.product_id for product in catalogue.products if product.is_active}
        dense = await self.qdrant.store.indexed_ids(category)
        try:
            lexical = self.bm25.indexed_ids(category)
        except FileNotFoundError:
            lexical = set()
        dense_missing = active - dense
        lexical_missing = active - lexical
        visual_count = sum(
            bool(product.visual_interpretation)
            for product in catalogue.products
            if product.is_active
        )
        return CatalogueHealthResponse(
            category=category,
            ready=not dense_missing and not lexical_missing,
            active_products=len(active),
            visual_interpretations_available=visual_count,
            dense_not_indexed=len(dense_missing),
            bm25_not_indexed=len(lexical_missing),
        )

