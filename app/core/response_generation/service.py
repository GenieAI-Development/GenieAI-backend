from __future__ import annotations

from app.schemas.internal import RerankedCandidate
from app.schemas.recommendation import ProductCard


class ResponseGenerator:
    """Build final user-facing cards only from already-selected candidates."""

    def product_card(self, candidate: RerankedCandidate) -> ProductCard:
        return ProductCard(
            product_id=candidate.verified.product.product_id,
            name=candidate.verified.cached_name or candidate.verified.product.name,
            price_lkr=candidate.verified.live_price_lkr,
            image_url=candidate.verified.image_url,
            vendor=candidate.verified.cached_vendor or candidate.verified.product.vendor,
            description=candidate.verified.cached_description,
        )

