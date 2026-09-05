"""Backfill Supabase ``products`` records for cakes missing from its cache.

Run with the project's runtime dependencies installed:

    python -m app.ingestion.sync_kapruka_gift_products

The script reads canonical product IDs from ``data/catalogue/cakes.json``, finds
the IDs absent from ``products``, fetches only those products from
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


SUPABASE_TABLE = "products"
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


def _price_amount(payload: dict[str, Any]) -> int | None:
    price = payload.get("price")
    amount = price.get("amount") if isinstance(price, dict) else None
    if amount is None:
        return None
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        return None
    return int(value) if value > 0 else None


def _record(product_id: str, fallback_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    images = payload.get("images")
    image_urls = [image for image in images if isinstance(image, str) and image.strip()] if isinstance(images, list) else []
    description = payload.get("description")
    description = description.strip() if isinstance(description, str) and description.strip() else fallback_name
    attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
    category = payload.get("category") if isinstance(payload.get("category"), dict) else {}
    return {
        "product_id": product_id,
        "name": payload.get("name") if isinstance(payload.get("name"), str) else fallback_name,
        "description": description,
        "display_description": description,
        "vendor": attributes.get("vendor") if isinstance(attributes.get("vendor"), str) else None,
        "category": category.get("slug") if isinstance(category.get("slug"), str) else "cakes",
        "price_lkr": _price_amount(payload),
        "main_image_url": _primary_image(images),
        "image_urls": image_urls,
        "is_active": payload.get("in_stock") if isinstance(payload.get("in_stock"), bool) else True,
    }


async def _existing_ids(client: httpx.AsyncClient) -> set[str]:
    ids: set[str] = set()
    offset = 0
    while True:
        response = await client.get(
            SUPABASE_TABLE,
            params={
                "select": "product_id",
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
        params={"on_conflict": "product_id"},
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
