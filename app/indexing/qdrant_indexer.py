from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from app.indexing.embedding_builder import EmbeddingClient, build_dense_text, dense_content_hash
from app.schemas.catalogue import CategoryCatalogue


class DenseVectorStore(Protocol):
    async def ensure_collection(self, category: str, recreate: bool = False) -> None: ...
    async def payload_hashes(self, category: str) -> dict[str, str]: ...
    async def indexed_ids(self, category: str) -> set[str]: ...
    async def upsert(
        self,
        category: str,
        product_ids: Sequence[str],
        vectors: Sequence[Sequence[float]],
        payloads: Sequence[dict[str, Any]],
    ) -> None: ...
    async def delete_products(self, category: str, product_ids: set[str]) -> None: ...


@dataclass(frozen=True)
class DenseIndexResult:
    upserted: int
    skipped: int
    removed: int


class QdrantIndexer:
    def __init__(self, store: DenseVectorStore, embeddings: EmbeddingClient) -> None:
        self.store = store
        self.embeddings = embeddings

    async def build(self, catalogue: CategoryCatalogue, rebuild: bool = False) -> DenseIndexResult:
        await self.store.ensure_collection(catalogue.category, recreate=rebuild)
        existing_hashes = {} if rebuild else await self.store.payload_hashes(catalogue.category)
        active = [product for product in catalogue.products if product.is_active]
        active_ids = {product.product_id for product in active}
        stale_ids = set(existing_hashes) - active_ids
        await self.store.delete_products(catalogue.category, stale_ids)

        changed = []
        texts = []
        hashes = []
        for product in active:
            text = build_dense_text(product)
            content_hash = dense_content_hash(text)
            if not rebuild and existing_hashes.get(product.product_id) == content_hash:
                continue
            changed.append(product)
            texts.append(text)
            hashes.append(content_hash)
        if changed:
            vectors = await self.embeddings.embed(texts)
            if len(vectors) != len(changed):
                raise RuntimeError("embedding response count does not match request")
            payloads = [
                {
                    "product_id": product.product_id,
                    "vendor": product.vendor,
                    "weight_kg": product.weight_kg,
                    "content_hash": content_hash,
                }
                for product, content_hash in zip(changed, hashes, strict=True)
            ]
            await self.store.upsert(
                catalogue.category,
                [product.product_id for product in changed],
                vectors,
                payloads,
            )
        return DenseIndexResult(
            upserted=len(changed), skipped=len(active) - len(changed), removed=len(stale_ids)
        )

