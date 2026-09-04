from __future__ import annotations

import re

from app.schemas.gift_box import GiftBoxState, GiftBoxWorkflowContext


_UNDER = re.compile(r"\b(?:under|below|up to|max(?:imum)?)\s*(?:rs\.?|lkr)?\s*([\d,]+)", re.I)
_OVER = re.compile(r"\b(?:over|above|at least|min(?:imum)?)\s*(?:rs\.?|lkr)?\s*([\d,]+)", re.I)
_BETWEEN = re.compile(
    r"\bbetween\s*(?:rs\.?|lkr)?\s*([\d,]+)\s*(?:and|to|-)\s*(?:rs\.?|lkr)?\s*([\d,]+)",
    re.I,
)
_COUNT = re.compile(r"\b(exactly\s+)?(\d{1,2})\s+(?:items?|products?)\b", re.I)
_FLEXIBLE_COUNT = re.compile(r"\b(?:around|about|roughly|approximately)\s+(\d{1,2})\s+(?:items?|products?)\b", re.I)
_RECIPIENT = re.compile(r"\bfor\s+(?:my\s+)?([a-z][a-z -]{1,40})(?=\s+(?:with|under|between|for|on)\b|[,.!?]|$)", re.I)
_THEME = re.compile(r"\b(?:theme|style)\s*(?:is|of|:)?\s*([a-z][a-z -]{1,40})(?=[,.!?]|$)", re.I)


def _amount(value: str) -> int:
    return int(value.replace(",", ""))


class GiftBoxContextResolver:
    def resolve(
        self,
        message: str,
        workflow_context: GiftBoxWorkflowContext | None,
        existing: GiftBoxState,
    ) -> GiftBoxState:
        values = existing.model_dump()
        if workflow_context is not None:
            values.update(workflow_context.model_dump(exclude_none=True))
            if workflow_context.item_count is not None:
                values["item_count_exact"] = True
        if match := _BETWEEN.search(message):
            values["budget_min_lkr"] = _amount(match.group(1))
            values["budget_max_lkr"] = _amount(match.group(2))
        else:
            if match := _UNDER.search(message):
                values["budget_max_lkr"] = _amount(match.group(1))
            if match := _OVER.search(message):
                values["budget_min_lkr"] = _amount(match.group(1))
        if match := _FLEXIBLE_COUNT.search(message):
            values["item_count"] = int(match.group(1))
            values["item_count_exact"] = False
        elif match := _COUNT.search(message):
            values["item_count"] = int(match.group(2))
            values["item_count_exact"] = True
        if match := _RECIPIENT.search(message):
            values["recipient"] = match.group(1).strip().casefold()
        if match := _THEME.search(message):
            values["theme"] = match.group(1).strip().casefold()
        return GiftBoxState.model_validate(values)

    @staticmethod
    def missing_fields(state: GiftBoxState) -> list[str]:
        missing = []
        if state.recipient is None and state.theme is None:
            missing.extend(["recipient", "theme"])
        if state.budget_min_lkr is None and state.budget_max_lkr is None:
            missing.append("budget_max_lkr")
        return missing
