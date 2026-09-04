from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from app.schemas.gift_box import GiftBoxState
from app.schemas.internal import RerankedCandidate


@dataclass(frozen=True)
class GiftBoxSolution:
    products: list[RerankedCandidate]
    total_price_lkr: int


class GiftBoxOptimizer:
    def optimize(
        self,
        candidates: list[RerankedCandidate],
        state: GiftBoxState,
        required_categories: set[str] | None = None,
    ) -> GiftBoxSolution | None:
        required_categories = required_categories or set()
        unique = {item.verified.product.product_id: item for item in candidates}
        ordered = sorted(
            unique.values(),
            key=lambda item: (-item.relevance_score, item.verified.product.product_id),
        )
        requested = state.item_count or 4
        pool_limit = min(len(ordered), max(12, requested + 6, len(required_categories) * 2))
        pool = ordered[:pool_limit]
        for category in required_categories:
            if any(item.verified.category == category for item in pool):
                continue
            replacement = next(
                (item for item in ordered[pool_limit:] if item.verified.category == category), None
            )
            if replacement is not None:
                if pool:
                    pool[-1] = replacement
                else:
                    pool.append(replacement)
        if state.item_count is not None and state.item_count_exact:
            sizes = [state.item_count]
        elif state.item_count is not None:
            sizes = range(max(1, state.item_count - 1), min(10, state.item_count + 1, len(pool)) + 1)
        else:
            sizes = range(1, min(4, len(pool)) + 1)
        best: tuple[float, tuple[RerankedCandidate, ...], int] | None = None
        for size in sizes:
            if size > len(pool):
                continue
            for selection in combinations(pool, size):
                total = sum(item.verified.live_price_lkr for item in selection)
                if state.budget_min_lkr is not None and total < state.budget_min_lkr:
                    continue
                if state.budget_max_lkr is not None and total > state.budget_max_lkr:
                    continue
                categories = {item.verified.category for item in selection}
                if not required_categories.issubset(categories):
                    continue
                relevance = sum(item.relevance_score for item in selection)
                diversity = len(categories) * 0.02
                utilization = 0.0
                if state.budget_max_lkr:
                    utilization = min(total / state.budget_max_lkr, 1.0) * 0.01
                score = relevance + diversity + utilization
                candidate = (score, selection, total)
                if best is None or candidate[0] > best[0]:
                    best = candidate
        if best is None:
            return None
        return GiftBoxSolution(products=list(best[1]), total_price_lkr=best[2])
