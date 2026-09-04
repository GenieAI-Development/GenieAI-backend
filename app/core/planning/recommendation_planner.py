from __future__ import annotations

import json
import re

from app.integrations.llm.reliable_executor import ReliableLLMExecutor
from app.schemas.internal import CategorySelection, QueryUnderstanding, RetrievalPlan


class RecommendationPlanner:
    def __init__(self, executor: ReliableLLMExecutor, fused_top_k: int = 20) -> None:
        self.executor = executor
        self.fused_top_k = fused_top_k

    async def plan(
        self, understanding: QueryUnderstanding, available_categories: list[str]
    ) -> list[RetrievalPlan]:
        scope = understanding.category_scope
        if not available_categories:
            return []
        allowed = set(available_categories)

        def terms(value: str) -> set[str]:
            normalized = set()
            for term in re.findall(r"[a-z0-9]+", value.casefold()):
                if term.endswith("ies") and len(term) > 3:
                    term = f"{term[:-3]}y"
                elif term.endswith("s") and not term.endswith("ss") and len(term) > 2:
                    term = term[:-1]
                normalized.add(term)
            return normalized

        categories = []
        for requested in scope.categories:
            exact = next(
                (
                    available
                    for available in available_categories
                    if available.casefold() == requested.casefold()
                ),
                None,
            )
            if exact is not None:
                categories.append(exact)
                continue
            requested_terms = terms(requested)
            matches = [
                available
                for available in available_categories
                if terms(available) and terms(available).issubset(requested_terms)
            ]
            if len(matches) == 1:
                categories.append(matches[0])
        categories = list(dict.fromkeys(categories))

        if not categories:

            def validate_selection(value: CategorySelection) -> CategorySelection:
                categories = list(dict.fromkeys(value.categories))
                if not categories or any(category not in allowed for category in categories):
                    raise ValueError("planner selected an unavailable category")
                value.categories = categories
                return value

            selection = await self.executor.execute(
                system_prompt=(
                    "Select 3-5 semantically relevant catalogue categories for the full "
                    "shopping query. Select only values from available_categories."
                ),
                user_prompt=json.dumps(
                    {
                        "query": understanding.original_query,
                        "interpreted_category_scope": scope.categories,
                        "available_categories": available_categories,
                    }
                ),
                response_model=CategorySelection,
                validator=validate_selection,
            )
            categories = selection.categories
        required = scope.user_explicit
        return [
            RetrievalPlan(
                category=category,
                query=understanding.original_query,
                candidate_limit=self.fused_top_k,
                stable_filters=understanding.stable_constraints,
                required=required,
            )
            for category in categories
        ]
