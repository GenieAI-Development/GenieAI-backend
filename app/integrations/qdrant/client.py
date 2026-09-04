from __future__ import annotations

from typing import Any, Sequence
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)


class QdrantVectorStore:
    def __init__(
        self,
        url: str,
        api_key: str | None,
        collection_prefix: str,
        dimension: int,
        client: AsyncQdrantClient | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.client = client or AsyncQdrantClient(
            url=url, api_key=api_key, timeout=timeout_seconds
        )
        self.collection_prefix = collection_prefix
        self.dimension = dimension

    def collection_name(self, category: str) -> str:
        return f"{self.collection_prefix}{category}"

    def point_id(self, category: str, product_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"genieai:{category}:{product_id}"))

    async def close(self) -> None:
        await self.client.close()

    async def ensure_collection(self, category: str, recreate: bool = False) -> None:
        name = self.collection_name(category)
        exists = await self.client.collection_exists(name)
        if recreate and exists:
            await self.client.delete_collection(name)
            exists = False
        if not exists:
            await self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
            )

    async def payload_hashes(self, category: str) -> dict[str, str]:
        if not await self.client.collection_exists(self.collection_name(category)):
            return {}
        records, cursor = await self.client.scroll(
            collection_name=self.collection_name(category),
            limit=256,
            with_payload=True,
            with_vectors=False,
        )
        all_records = list(records)
        while cursor is not None:
            records, cursor = await self.client.scroll(
                collection_name=self.collection_name(category),
                limit=256,
                offset=cursor,
                with_payload=True,
                with_vectors=False,
            )
            all_records.extend(records)
        return {
            str(point.payload["product_id"]): str(point.payload["content_hash"])
            for point in all_records
            if point.payload and "product_id" in point.payload and "content_hash" in point.payload
        }

    async def indexed_ids(self, category: str) -> set[str]:
        return set((await self.payload_hashes(category)).keys())

    async def upsert(
        self,
        category: str,
        product_ids: Sequence[str],
        vectors: Sequence[Sequence[float]],
        payloads: Sequence[dict[str, Any]],
    ) -> None:
        points = [
            PointStruct(
                id=self.point_id(category, product_id), vector=list(vector), payload=payload
            )
            for product_id, vector, payload in zip(product_ids, vectors, payloads, strict=True)
        ]
        if points:
            await self.client.upsert(self.collection_name(category), points=points, wait=True)

    async def delete_products(self, category: str, product_ids: set[str]) -> None:
        if not product_ids:
            return
        await self.client.delete(
            collection_name=self.collection_name(category),
            points_selector=PointIdsList(
                points=[self.point_id(category, product_id) for product_id in product_ids]
            ),
            wait=True,
        )

    async def search(
        self,
        category: str,
        vector: Sequence[float],
        limit: int,
        vendor: str | None = None,
        excluded_vendors: set[str] | None = None,
        exact_weight_kg: float | None = None,
        excluded_product_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        must = []
        must_not = []
        if vendor:
            must.append(FieldCondition(key="vendor", match=MatchValue(value=vendor)))
        if excluded_vendors:
            must_not.extend(
                FieldCondition(key="vendor", match=MatchValue(value=value))
                for value in excluded_vendors
            )
        if exact_weight_kg is not None:
            must.append(FieldCondition(key="weight_kg", match=MatchValue(value=exact_weight_kg)))
        if excluded_product_ids:
            must_not.extend(
                FieldCondition(key="product_id", match=MatchValue(value=value))
                for value in excluded_product_ids
            )
        result = await self.client.query_points(
            collection_name=self.collection_name(category),
            query=list(vector),
            query_filter=Filter(must=must or None, must_not=must_not or None),
            limit=limit,
            with_payload=True,
        )
        return [
            (str(point.payload["product_id"]), float(point.score))
            for point in result.points
            if point.payload and "product_id" in point.payload
        ]
