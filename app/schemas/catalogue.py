from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CATEGORY_PATTERN = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


def normalize_category(value: str) -> str:
    normalized = value.strip().casefold()
    if not CATEGORY_PATTERN.fullmatch(normalized):
        raise ValueError("category must be a lowercase slug")
    return normalized


class CatalogueProduct(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    product_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1)
    vendor: str = Field(min_length=1, max_length=500)
    weight_kg: float | None = Field(default=None, gt=0)
    price_snapshot_lkr: int | None = Field(default=None, gt=0)
    is_active: bool
    visual_interpretation: str | None = None
    visual_interpretation_model: str | None = None

    @field_validator("visual_interpretation", "visual_interpretation_model")
    @classmethod
    def empty_optional_text_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_visual_provenance(self) -> "CatalogueProduct":
        if self.visual_interpretation is None:
            self.visual_interpretation_model = None
        return self


class CategoryCatalogue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    products: list[CatalogueProduct] = Field(default_factory=list)

    @field_validator("category")
    @classmethod
    def category_slug(cls, value: str) -> str:
        return normalize_category(value)

    @model_validator(mode="after")
    def unique_product_ids(self) -> "CategoryCatalogue":
        ids = [product.product_id for product in self.products]
        duplicates = sorted({product_id for product_id in ids if ids.count(product_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate product_id values: {', '.join(duplicates)}")
        return self

