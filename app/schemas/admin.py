from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.catalogue import normalize_category


class CategoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str

    @field_validator("category")
    @classmethod
    def category_slug(cls, value: str) -> str:
        return normalize_category(value)


class ProductImportRequest(CategoryRequest):
    product_ids: list[str] = Field(min_length=1)

    @field_validator("product_ids")
    @classmethod
    def validate_product_ids(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            product_id = value.strip()
            if not product_id:
                raise ValueError("product IDs must not be empty")
            if product_id not in seen:
                seen.add(product_id)
                normalized.append(product_id)
        return normalized


class ProductImportResponse(BaseModel):
    category: str
    imported_count: int
    failed_product_ids: list[str]


class VisualInterpretationItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    product_id: str = Field(min_length=1)
    visual_interpretation: str = Field(min_length=1)


class VisualInterpretationImportRequest(CategoryRequest):
    model_name: str | None = Field(default=None, min_length=1)
    replace_existing: bool = False
    items: list[VisualInterpretationItem] = Field(min_length=1)


class VisualInterpretationImportResponse(BaseModel):
    category: str
    updated_count: int
    skipped_count: int


class IndexBuildRequest(CategoryRequest):
    rebuild: bool = False


class IndexBuildResponse(BaseModel):
    category: str
    dense_upserted: int
    dense_skipped: int
    dense_removed: int
    bm25_documents: int
    ready: bool


class CatalogueHealthResponse(BaseModel):
    category: str
    ready: bool
    active_products: int
    visual_interpretations_available: int
    dense_not_indexed: int
    bm25_not_indexed: int

