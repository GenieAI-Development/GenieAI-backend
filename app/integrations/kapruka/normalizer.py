from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.schemas.catalogue import CatalogueProduct, normalize_category


class ProductNormalizationError(ValueError):
    """A Kapruka response cannot safely become canonical or live data."""


_NUMBER = r"(\d+(?:\.\d+)?)"
_KG = re.compile(_NUMBER + r"\s*(?:kg|kgs|kilograms?)\b", re.IGNORECASE)
_LB = re.compile(_NUMBER + r"\s*(?:lb|lbs|pounds?)\b", re.IGNORECASE)
_LB_TO_KG = Decimal("0.45359237")


def normalize_weight(description: str, raw_weight: object = None) -> float | None:
    sources = [description]
    if isinstance(raw_weight, str):
        sources.append(raw_weight)
    for source in sources:
        match = _KG.search(source)
        if match:
            return float(Decimal(match.group(1)))
    for source in sources:
        match = _LB.search(source)
        if match:
            kilograms = (Decimal(match.group(1)) * _LB_TO_KG).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )
            return float(kilograms)
    return None


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductNormalizationError(f"missing or invalid {field}")
    return value.strip()


def _price_amount(value: object) -> int | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ProductNormalizationError("invalid price.amount") from None
    if amount <= 0:
        raise ProductNormalizationError("invalid price.amount")
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def normalize_product(payload: dict[str, Any], requested_category: str) -> CatalogueProduct:
    category = payload.get("category")
    category_slug = category.get("slug") if isinstance(category, dict) else None
    expected = normalize_category(requested_category)
    if not isinstance(category_slug, str) or normalize_category(category_slug) != expected:
        raise ProductNormalizationError("product category does not match requested category")

    attributes = payload.get("attributes")
    attributes = attributes if isinstance(attributes, dict) else {}
    price = payload.get("price")
    price = price if isinstance(price, dict) else {}
    description = _required_text(payload.get("description"), "description")
    return CatalogueProduct(
        product_id=_required_text(payload.get("id"), "id"),
        name=_required_text(payload.get("name"), "name"),
        description=description,
        vendor=_required_text(attributes.get("vendor"), "attributes.vendor"),
        weight_kg=normalize_weight(description, attributes.get("weight")),
        price_snapshot_lkr=_price_amount(price.get("amount")),
        is_active=True,
    )


def extract_live_product(payload: dict[str, Any]) -> tuple[int, bool, str | None]:
    price = payload.get("price")
    price = price if isinstance(price, dict) else {}
    amount = _price_amount(price.get("amount"))
    if amount is None:
        raise ProductNormalizationError("live price is missing")
    in_stock = payload.get("in_stock")
    if not isinstance(in_stock, bool):
        raise ProductNormalizationError("in_stock must be boolean")
    image_url: str | None = None
    images = payload.get("images")
    if isinstance(images, list) and images:
        primary = images[0]
        if isinstance(primary, str):
            image_url = primary.strip() or None
        elif isinstance(primary, dict):
            value = primary.get("url") or primary.get("image_url")
            if isinstance(value, str):
                image_url = value.strip() or None
    return amount, in_stock, image_url
