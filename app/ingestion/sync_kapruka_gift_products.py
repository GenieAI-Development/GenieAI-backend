"""Backfill Supabase gift-product records for cakes missing from its cache.

Run with the project's runtime dependencies installed:

    python -m app.ingestion.sync_kapruka_gift_products

The script reads canonical product IDs from ``data/catalogue/cakes.json``, finds
the IDs absent from ``kapruka_gift_products``, fetches only those products from
Kapruka MCP, and upserts the resulting cache records into Supabase.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from app.config.settings import Settings
from app.repositories.catalogue_repository import JsonCatalogueRepository


SUPABASE_TABLE = "kapruka_gift_products"
ASSIGNED_CATEGORY = "cakes_and_desserts"
MATCHED_KEYWORD = "cakes"
PAGE_SIZE = 1_000


def _env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        env_path = Path(".env")
        if env_path.is_file():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                key, separator, raw_value = line.partition("=")
                if separator and key.strip() == name:
                    value = raw_value.strip().strip('"').strip("'")
                    break
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _primary_image(images: object) -> str | None:
    if not isinstance(images, list) or not images:
        return None
    first = images[0]
    if isinstance(first, str):
        return first.strip() or None
    if isinstance(first, dict):
        value = first.get("url") or first.get("image_url")
        if isinstance(value, str):
            return value.strip() or None
    return None


def _product_url(payload: dict[str, Any]) -> str | None:
    for key in ("product_url", "url", "canonical_url", "link"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    urls = payload.get("urls")
    if isinstance(urls, dict):
        for key in ("product", "canonical", "url"):
            value = urls.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _price_amount(payload: dict[str, Any]) -> str | None:
    price = payload.get("price")
    amount = price.get("amount") if isinstance(price, dict) else None
    if amount is None:
        return None
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        return None
    return str(value) if value > 0 else None


def _record(product_id: str, fallback_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    images = payload.get("images")
    images = images if isinstance(images, list) else []
    category = payload.get("category")
    return {
        "assigned_category": ASSIGNED_CATEGORY,
        "product_id": product_id,
        "matched_keyword": MATCHED_KEYWORD,
        "name": payload.get("name") if isinstance(payload.get("name"), str) else fallback_name,
        "summary": payload.get("summary") if isinstance(payload.get("summary"), str) else None,
        "description": payload.get("description") if isinstance(payload.get("description"), str) else None,
        "price_amount": _price_amount(payload),
        "currency": "LKR",
        "in_stock": payload.get("in_stock") if isinstance(payload.get("in_stock"), bool) else None,
        "stock_level": payload.get("stock_level") if isinstance(payload.get("stock_level"), str) else None,
        "image_url": _primary_image(images),
        "images": images,
        "kapruka_category": category if isinstance(category, dict) else None,
        "product_url": _product_url(payload),
        "raw_product": payload,
    }


async def _existing_ids(client: httpx.AsyncClient) -> set[str]:
    ids: set[str] = set()
    offset = 0
    while True:
        response = await client.get(
            SUPABASE_TABLE,
            params={
                "select": "product_id",
                "assigned_category": f"eq.{ASSIGNED_CATEGORY}",
                "offset": offset,
                "limit": PAGE_SIZE,
            },
        )
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise RuntimeError("Supabase returned an invalid product ID page")
        ids.update(str(item["product_id"]) for item in page if "product_id" in item)
        if len(page) < PAGE_SIZE:
            return ids
        offset += PAGE_SIZE


async def _upsert(client: httpx.AsyncClient, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    response = await client.post(
        SUPABASE_TABLE,
        params={"on_conflict": "assigned_category,product_id"},
        headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        json=records,
    )
    response.raise_for_status()


async def run(*, dry_run: bool, limit: int | None) -> None:
    settings = Settings()
    repository = JsonCatalogueRepository(settings.catalogue_dir)
    catalogue = repository.load_category("cakes")
    canonical = {product.product_id: product for product in catalogue.products if product.is_active}

    base_url = _env("NEXT_PUBLIC_SUPABASE_URL").rstrip("/") + "/rest/v1/"
    secret_key = _env("SUPABASE_SECRET_KEY")
    headers = {"apikey": secret_key, "Authorization": f"Bearer {secret_key}"}
    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30.0) as database:
        existing = await _existing_ids(database)
        missing_ids = sorted(set(canonical) - existing)
        if limit is not None:
            missing_ids = missing_ids[:limit]
        print(f"canonical_active={len(canonical)}")
        print(f"existing_cache_records={len(existing)}")
        print(f"missing_count={len(missing_ids)}")
        print("missing_ids=" + ",".join(missing_ids))
        if dry_run or not missing_ids:
            return

        from app.integrations.kapruka.client import McpKaprukaClient

        kapruka = McpKaprukaClient(
            url=settings.kapruka_mcp_url,
            command=settings.kapruka_mcp_command,
            args=settings.kapruka_mcp_args,
            timeout_seconds=settings.kapruka_timeout_seconds,
            max_attempts=settings.kapruka_max_attempts,
            rate_limit_per_minute=settings.kapruka_rate_limit_per_minute,
        )
        records: list[dict[str, Any]] = []
        try:
            for product_id in missing_ids:
                product = canonical[product_id]
                try:
                    payload = await kapruka.get_product(product_id)
                    records.append(_record(product_id, product.name, payload))
                    print(f"fetched={product_id}")
                except Exception as exc:
                    print(f"failed={product_id} error={type(exc).__name__}")
            await _upsert(database, records)
            print(f"upserted_count={len(records)}")
        finally:
            await kapruka.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Only print the missing product IDs.")
    parser.add_argument("--limit", type=int, help="Process at most this many missing products.")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))


if __name__ == "__main__":
    main()
