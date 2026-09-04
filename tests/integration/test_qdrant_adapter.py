import pytest
from qdrant_client import AsyncQdrantClient

from app.integrations.qdrant.client import QdrantVectorStore


@pytest.mark.asyncio
async def test_qdrant_collection_payload_search_and_delete_contract():
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantVectorStore(
        url="http://unused",
        api_key=None,
        collection_prefix="kapruka_",
        dimension=2,
        client=client,
    )
    assert store.collection_name("cakes") == "kapruka_cakes"
    await store.ensure_collection("cakes")
    await store.upsert(
        "cakes",
        ["P1"],
        [[1.0, 0.0]],
        [
            {
                "product_id": "P1",
                "vendor": "Vendor",
                "weight_kg": 1.0,
                "content_hash": "hash",
            }
        ],
    )
    assert await store.payload_hashes("cakes") == {"P1": "hash"}
    assert (await store.search("cakes", [1.0, 0.0], 5))[0][0] == "P1"
    await store.delete_products("cakes", {"P1"})
    assert await store.indexed_ids("cakes") == set()
    await client.close()

