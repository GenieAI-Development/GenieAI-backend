from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GiftBoxWorkflowContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient: str | None = Field(default=None, max_length=200)
    theme: str | None = Field(default=None, max_length=200)
    item_count: int | None = Field(default=None, ge=1, le=10)
    budget_min_lkr: int | None = Field(default=None, gt=0)
    budget_max_lkr: int | None = Field(default=None, gt=0)

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, data: object) -> object:
        if isinstance(data, dict):
            null_fields = [key for key, value in data.items() if value is None]
            if null_fields:
                raise ValueError(f"explicit null is not allowed for: {', '.join(null_fields)}")
        return data

    @field_validator("recipient", "theme")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_budget_range(self) -> "GiftBoxWorkflowContext":
        if (
            self.budget_min_lkr is not None
            and self.budget_max_lkr is not None
            and self.budget_max_lkr < self.budget_min_lkr
        ):
            raise ValueError("budget_max_lkr must be greater than or equal to budget_min_lkr")
        return self


class GiftBoxState(BaseModel):
    recipient: str | None = None
    theme: str | None = None
    item_count: int | None = Field(default=None, ge=1, le=10)
    item_count_exact: bool = True
    budget_min_lkr: int | None = Field(default=None, gt=0)
    budget_max_lkr: int | None = Field(default=None, gt=0)
