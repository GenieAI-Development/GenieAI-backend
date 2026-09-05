from __future__ import annotations

from typing import Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.gift_box import GiftBoxWorkflowContext


RequestType = Literal["product_recommendation", "gift_box"]
ResponseType = Literal[
    "recommendation",
    "limited_results",
    "clarification",
    "workflow_mismatch",
    "delivery_unavailable",
    "temporary_unavailable",
]


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_type: RequestType
    session_id: UUID | None = None
    message: str = Field(min_length=1, max_length=2000)
    workflow_context: GiftBoxWorkflowContext | None = None

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_workflow_context(self) -> "RecommendationRequest":
        if self.request_type == "product_recommendation" and self.workflow_context is not None:
            raise ValueError("workflow_context must be omitted for product_recommendation")
        return self


class ProductCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    name: str
    price_lkr: int = Field(gt=0)
    image_url: str = Field(min_length=1)
    vendor: str
    description: str | None = None


class ResponseBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    session_id: str
    request_type: RequestType
    response_type: ResponseType
    message: str


class SmartShoppingResponse(ResponseBase):
    request_type: Literal["product_recommendation"]
    response_type: Literal["recommendation", "limited_results"]
    result_count: int = Field(ge=0)
    products: list[ProductCard]


class GiftBoxBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    products: list[ProductCard]
    total_price_lkr: int = Field(ge=0)
    item_count: int = Field(ge=0)


class GiftBoxResponse(ResponseBase):
    request_type: Literal["gift_box"]
    response_type: Literal["recommendation", "limited_results"]
    bundle: GiftBoxBundle


class ClarificationResponse(ResponseBase):
    response_type: Literal["clarification"]
    missing_fields: list[str]


class WorkflowMismatchResponse(ResponseBase):
    response_type: Literal["workflow_mismatch"]
    suggested_workflow: RequestType


class DeliveryUnavailableResponse(ResponseBase):
    response_type: Literal["delivery_unavailable"]


class TemporaryUnavailableResponse(ResponseBase):
    response_type: Literal["temporary_unavailable"]


RuntimeResponse = Union[
        SmartShoppingResponse,
        GiftBoxResponse,
        ClarificationResponse,
        WorkflowMismatchResponse,
        DeliveryUnavailableResponse,
        TemporaryUnavailableResponse,
    ]


class ValidationIssue(BaseModel):
    field: str
    issue: str


class ErrorDetail(BaseModel):
    code: Literal["INVALID_REQUEST"] = "INVALID_REQUEST"
    message: str
    details: list[ValidationIssue]


class ErrorEnvelope(BaseModel):
    request_id: str
    session_id: str | None = None
    error: ErrorDetail
