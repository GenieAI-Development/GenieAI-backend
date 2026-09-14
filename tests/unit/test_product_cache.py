import pytest

from app.integrations.supabase.product_cache import (
    CachedProductNotFoundError,
    SupabaseProductCache,
)


class FakeResponse:
    def __init__(self, rows):
        self.rows = rows

    def raise_for_status(self):
        return None

    def json(self):
        return self.rows


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.params = None

    async def get(self, table, params):
        self.params = params
        return FakeResponse(self.rows)


@pytest.mark.asyncio
async def test_product_cache_scopes_lookup_to_retrieval_category():
    cache = SupabaseProductCache(None, None)
    client = FakeClient([])
    cache._client = client

    with pytest.raises(CachedProductNotFoundError):
        await cache.get_product("CAKE-1", "cakes")

    assert client.params["product_id"] == "eq.CAKE-1"
    assert client.params["category"] == "eq.cakes"
