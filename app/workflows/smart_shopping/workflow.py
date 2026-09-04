from __future__ import annotations

from app.schemas.internal import RerankedCandidate
from app.core.response_generation.service import ResponseGenerator
from app.schemas.recommendation import SmartShoppingResponse


class SmartShoppingWorkflow:
    def __init__(
        self, max_products: int = 12, response_generator: ResponseGenerator | None = None
    ) -> None:
        self.max_products = max_products
        self.response_generator = response_generator or ResponseGenerator()

    def build_response(
        self,
        *,
        request_id: str,
        session_id: str,
        candidates: list[RerankedCandidate],
    ) -> SmartShoppingResponse:
        selected = candidates[: self.max_products]
        response_type = "recommendation" if len(selected) >= self.max_products else "limited_results"
        if selected:
            message = (
                "I found the strongest currently available matches for your request."
                if response_type == "recommendation"
                else "I found a limited set of currently available products that meet your requirements."
            )
        else:
            message = "I couldn't find a currently available product that meets all of your requirements."
        products = [self.response_generator.product_card(item) for item in selected]
        return SmartShoppingResponse(
            request_id=request_id,
            session_id=session_id,
            request_type="product_recommendation",
            response_type=response_type,
            message=message,
            result_count=len(products),
            products=products,
        )
