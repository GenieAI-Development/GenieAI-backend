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

        def normalized_terms(value: str) -> list[str]:
            terms = []
            for term in re.findall(r"[a-z0-9]+", value.casefold()):
                if term.endswith("ies") and len(term) > 3:
                    term = f"{term[:-3]}y"
                elif term.endswith("s") and not term.endswith("ss") and len(term) > 2:
                    term = term[:-1]
                terms.append(term)
            return terms

        aliases = {
            "cake": "cakes",
            "chocolate": "chocolates",
            "flower": "flowers",
            "rose": "flowers",
            "bouquet": "flowers",
            "perfume": "perfumes",
            "fragrance": "perfumes",
            "cologne": "perfumes",
        }
        # New catalogue categories remain discoverable without requiring a
        # code change; the final slug word acts as their default product type.
        for available in available_categories:
            terms = normalized_terms(available)
            if terms:
                aliases.setdefault(terms[-1], available)

        def category_from_phrase(phrase: str) -> str | None:
            # "Chocolate cake" is a cake: choose the final product-type word,
            # not every category-related word in the phrase. "Cake with
            # chocolates" likewise keeps cake as the requested product type.
            product_phrase = re.split(r"\bwith\b|\bfilled\b|\btopped\b", phrase, maxsplit=1)[0]
            for term in reversed(normalized_terms(product_phrase)):
                category = aliases.get(term)
                if category in allowed:
                    return category
            return None

        def explicit_category_phrases(query: str) -> list[str]:
            # Multiple retrieval categories are allowed only when the user
            # explicitly joins product types, e.g. "cakes and chocolates".
            if re.search(r"\b(?:and|or)\b|[,&/]", query.casefold()):
                return [part for part in re.split(r"\b(?:and|or)\b|[,&/]", query) if part.strip()]
            return [query]

        categories = [
            category
            for phrase in explicit_category_phrases(understanding.original_query)
            if (category := category_from_phrase(phrase)) is not None
        ]

        # If the user's wording has no known product-type term, use the
        # structured category scope produced by query understanding.
        if not categories:
            categories = [
                category
                for requested in scope.categories
                if (category := category_from_phrase(requested)) is not None
            ]
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
                    "Select one or more semantically relevant catalogue categories for the full "
                    "shopping query. Select only values from available_categories. "
                    "Select the product type, not descriptive modifiers: a chocolate "
                    "cake belongs to cakes, not chocolates. Select multiple categories "
                    "only when the user explicitly requests multiple product types."
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
