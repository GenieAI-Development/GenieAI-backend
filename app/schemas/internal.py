from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.catalogue import CatalogueProduct


class CategoryScope(BaseModel):
    mode: Literal["unspecified", "single_category", "multiple_categories", "broad"]
    categories: list[str] = Field(default_factory=list)
    user_explicit: bool = False


class StableConstraints(BaseModel):
    vendor: str | None = None
    exact_weight_kg: float | None = Field(default=None, gt=0)
    excluded_vendors: list[str] = Field(default_factory=list)
    excluded_product_ids: list[str] = Field(default_factory=list)


class SoftConstraints(BaseModel):
    target_weight_kg: float | None = Field(default=None, gt=0)


class VolatileConstraints(BaseModel):
    min_price: int | None = Field(default=None, gt=0)
    max_price: int | None = Field(default=None, gt=0)
    requires_in_stock: bool = True

    @model_validator(mode="after")
    def valid_range(self) -> "VolatileConstraints":
        if self.min_price and self.max_price and self.max_price < self.min_price:
            raise ValueError("max_price must be greater than or equal to min_price")
        return self


class DeliveryRequest(BaseModel):
    city: str
    delivery_date: date


class ClarificationDecision(BaseModel):
    required: bool = False
    reason: str | None = None
    missing_information: list[str] = Field(default_factory=list)


class WorkflowMismatchDecision(BaseModel):
    detected: bool = False
    suggested_workflow: Literal["product_recommendation", "gift_box"] | None = None


class QueryUnderstanding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_query: str
    category_scope: CategoryScope
    stable_constraints: StableConstraints = Field(default_factory=StableConstraints)
    soft_constraints: SoftConstraints = Field(default_factory=SoftConstraints)
    volatile_constraints: VolatileConstraints = Field(default_factory=VolatileConstraints)
    mandatory_semantic_requirements: list[str] = Field(default_factory=list)
    mandatory_semantic_exclusions: list[str] = Field(default_factory=list)
    delivery_request: DeliveryRequest | None = None
    clarification: ClarificationDecision = Field(default_factory=ClarificationDecision)
    workflow_mismatch: WorkflowMismatchDecision = Field(default_factory=WorkflowMismatchDecision)


class CategorySelection(BaseModel):
    categories: list[str] = Field(min_length=1, max_length=5)


class RetrievalPlan(BaseModel):
    category: str
    query: str
    candidate_limit: int = Field(ge=1, le=60)
    stable_filters: StableConstraints
    required: bool = False


class RetrievalHit(BaseModel):
    product_id: str
    category: str
    dense_rank: int | None = None
    bm25_rank: int | None = None
    rrf_score: float


class VerifiedCandidate(BaseModel):
    product: CatalogueProduct
    category: str
    live_price_lkr: int = Field(gt=0)
    image_url: str
    retrieval: RetrievalHit


class RerankDecision(BaseModel):
    product_id: str
    eligible: bool
    relevance_score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=220)
    semantic_requirement_failures: list[str] = Field(default_factory=list)
    semantic_exclusion_violations: list[str] = Field(default_factory=list)


class RerankOutput(BaseModel):
    decisions: list[RerankDecision]


class RerankedCandidate(BaseModel):
    verified: VerifiedCandidate
    relevance_score: float
    reason: str

