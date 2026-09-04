from __future__ import annotations

from app.optimizers.gift_box_optimizer import GiftBoxOptimizer
from app.core.response_generation.service import ResponseGenerator
from app.schemas.gift_box import GiftBoxState
from app.schemas.internal import RerankedCandidate
from app.schemas.recommendation import (
    ClarificationResponse,
    GiftBoxBundle,
    GiftBoxResponse,
)


class GiftBoxWorkflow:
    def __init__(
        self, optimizer: GiftBoxOptimizer, response_generator: ResponseGenerator | None = None
    ) -> None:
        self.optimizer = optimizer
        self.response_generator = response_generator or ResponseGenerator()

    def build_response(
        self,
        *,
        request_id: str,
        session_id: str,
        state: GiftBoxState,
        candidates: list[RerankedCandidate],
        required_categories: set[str],
    ) -> GiftBoxResponse | ClarificationResponse:
        solution = self.optimizer.optimize(candidates, state, required_categories)
        if solution is None:
            hints: list[str] = []
            if state.item_count is not None:
                hints.append("item_count")
            if state.budget_max_lkr is not None:
                hints.append("budget_max_lkr")
            return ClarificationResponse(
                request_id=request_id,
                session_id=session_id,
                request_type="gift_box",
                response_type="clarification",
                message=(
                    "I couldn't make a valid box with those constraints. "
                    "Please relax the item count, budget, or required product categories."
                ),
                missing_fields=hints,
            )
        cards = [self.response_generator.product_card(item) for item in solution.products]
        return GiftBoxResponse(
            request_id=request_id,
            session_id=session_id,
            request_type="gift_box",
            response_type="recommendation",
            message="I created a gift box that satisfies your available budget and item constraints.",
            bundle=GiftBoxBundle(
                products=cards,
                total_price_lkr=solution.total_price_lkr,
                item_count=len(cards),
            ),
        )
