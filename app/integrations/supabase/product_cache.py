from __future__ import annotations

from typing import Any

import httpx


class ProductCacheError(RuntimeError):
    """A cached product record cannot be read from Supabase."""


class CachedProductNotFoundError(ProductCacheError):
    """A product is absent from the Supabase cache."""


class SupabaseProductCache:
    """Read cached Kapruka product commerce data from Supabase."""

    def __init__(
        self,
        url: str | None,
        secret_key: str | None,
        table: str = "products",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.table = table
        self._enabled = bool(url and secret_key)
        self._client = (
            httpx.AsyncClient(
                base_url=f"{url.rstrip('/')}/rest/v1/",
                headers={"apikey": secret_key, "Authorization": f"Bearer {secret_key}"},
                timeout=timeout_seconds,
            )
            if self._enabled and url and secret_key
            else None
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def get_product(self, product_id: str) -> dict[str, Any]:
        if self._client is None:
            raise ProductCacheError("Supabase product cache is not configured")
        response = await self._client.get(
            self.table,
            params={
                "select": "product_id,name,description,display_description,vendor,price_lkr,main_image_url,image_urls,is_active",
                "product_id": f"eq.{product_id}",
                "limit": 1,
            },
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            raise CachedProductNotFoundError(f"cached product is missing: {product_id}")
        record = rows[0]
        images = record.get("image_urls")
        if not isinstance(images, list):
            images = []
        if not images and isinstance(record.get("main_image_url"), str):
            images = [record["main_image_url"]]
        description = record.get("display_description")
        if not isinstance(description, str) or not description.strip():
            description = record.get("description")
        return {
            "id": product_id,
            "name": record.get("name") if isinstance(record.get("name"), str) else None,
            "description": description.strip() if isinstance(description, str) else None,
            "vendor": record.get("vendor") if isinstance(record.get("vendor"), str) else None,
            "price": {"amount": record.get("price_lkr")},
            "in_stock": record.get("is_active"),
            "images": images,
        }
