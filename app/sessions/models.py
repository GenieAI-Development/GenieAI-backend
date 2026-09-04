from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.gift_box import GiftBoxState


class ProductSearchState(BaseModel):
    query_understanding: dict[str, object] = Field(default_factory=dict)
    previous_product_ids: list[str] = Field(default_factory=list)


class RecommendationSession(BaseModel):
    session_id: str
    product_search_state: ProductSearchState = Field(default_factory=ProductSearchState)
    gift_box_state: GiftBoxState = Field(default_factory=GiftBoxState)

