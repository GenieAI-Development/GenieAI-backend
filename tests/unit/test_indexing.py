import pytest

from app.indexing.bm25_indexer import BM25Indexer, build_bm25_text
from app.indexing.embedding_builder import build_dense_text, dense_content_hash
from app.indexing.qdrant_indexer import QdrantIndexer
from app.schemas.catalogue import CategoryCatalogue, CatalogueProduct


def product(product_id="P1", visual=None, active=True):
    return CatalogueProduct(
        product_id=product_id,
        name="Rose Cake",
        description="Vanilla floral cake",
        vendor="Vendor",
        weight_kg=1.0,
        is_active=active,
        visual_interpretation=visual,
    )


def test_dense_text_and_hash_are_deterministic():
    plain = product()
    visual = product(visual="Pastel roses")
    assert build_dense_text(plain) == "Vanilla floral cake"
    assert build_dense_text(visual) == "Vanilla floral cake\n\nPastel roses"
    assert dense_content_hash(build_dense_text(plain)) == dense_content_hash(build_dense_text(plain))


def test_bm25_text_excludes_visual_interpretation():
    text = build_bm25_text(product(visual="SECRET_VISUAL"), "cakes")
    assert "SECRET_VISUAL" not in text
    assert "Rose Cake" in text


def test_bm25_persistence_and_category_independence(tmp_path):
    indexer = BM25Indexer(tmp_path)
    cakes = CategoryCatalogue(category="cakes", products=[product("C1")])
    flowers = CategoryCatalogue(category="flowers", products=[product("F1")])
    indexer.build(cakes)
    indexer.build(flowers)
    assert indexer.indexed_ids("cakes") == {"C1"}
    assert indexer.indexed_ids("flowers") == {"F1"}
    assert indexer.search("cakes", "rose cake", 5)[0][0] == "C1"


def test_empty_bm25_category_persists_safely(tmp_path):
    indexer = BM25Indexer(tmp_path)
    assert indexer.build(CategoryCatalogue(category="cakes", products=[])) == 0
    assert indexer.indexed_ids("cakes") == set()
    assert indexer.search("cakes", "anything", 5) == []


class FakeEmbeddings:
    def __init__(self):
        self.calls = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        return [[0.1, 0.2] for _ in texts]


class FakeStore:
    def __init__(self):
        self.hashes = {}
        self.upserts = []
        self.deleted = set()
        self.recreated = False

    async def ensure_collection(self, category, recreate=False):
        self.recreated = recreate

    async def payload_hashes(self, category):
        return dict(self.hashes)

    async def indexed_ids(self, category):
        return set(self.hashes)

    async def delete_products(self, category, product_ids):
        self.deleted |= product_ids

    async def upsert(self, category, product_ids, vectors, payloads):
        self.upserts.extend(payloads)


@pytest.mark.asyncio
async def test_qdrant_payload_and_hash_skip():
    item = product()
    store = FakeStore()
    embeddings = FakeEmbeddings()
    indexer = QdrantIndexer(store, embeddings)
    catalogue = CategoryCatalogue(category="cakes", products=[item])
    first = await indexer.build(catalogue)
    assert first.upserted == 1
    assert set(store.upserts[0]) == {"product_id", "vendor", "weight_kg", "content_hash"}
    store.hashes = {"P1": store.upserts[0]["content_hash"]}
    second = await indexer.build(catalogue)
    assert second.skipped == 1
    assert len(embeddings.calls) == 1


@pytest.mark.asyncio
async def test_changed_hash_reindexes_and_inactive_is_removed():
    store = FakeStore()
    store.hashes = {"P1": "old", "INACTIVE": "hash"}
    embeddings = FakeEmbeddings()
    result = await QdrantIndexer(store, embeddings).build(
        CategoryCatalogue(category="cakes", products=[product("P1")])
    )
    assert result.upserted == 1
    assert store.deleted == {"INACTIVE"}
