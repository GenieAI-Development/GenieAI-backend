from __future__ import annotations

import json

from app.integrations.llm.reliable_executor import ReliableLLMExecutor
from app.schemas.internal import QueryUnderstanding


class QueryUnderstandingService:
    def __init__(self, executor: ReliableLLMExecutor) -> None:
        self.executor = executor

    async def understand(
        self,
        message: str,
        request_type: str,
        previous_state: dict[str, object] | None = None,
    ) -> QueryUnderstanding:
        system_prompt = """You are GenieAI's shared query-understanding component.
Return only the requested structured contract. Preserve the user's exact message in
original_query. The frontend request_type is authoritative: detect but never switch a
clear workflow mismatch. Gift Box recipient, theme, item_count and budget range are
not owned by this component. Classify price/stock as volatile, vendor/product/explicit
exact weight as stable, ordinary weight as soft, and visual/style must/must-not rules
as mandatory semantic requirements/exclusions. Stock is always required. Ask for
clarification only when retrieval cannot be meaningfully targeted. Delivery is a
request-level city/date value. Do not emit confidence scores."""
        user_prompt = json.dumps(
            {
                "request_type": request_type,
                "message": message,
                "previous_recommendation_state": previous_state or {},
            },
            default=str,
        )

        def preserve_original_query(value: QueryUnderstanding) -> QueryUnderstanding:
            if value.original_query != message:
                raise ValueError("original_query must exactly preserve the current message")
            return value

        result = await self.executor.execute(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=QueryUnderstanding,
            validator=preserve_original_query,
        )
        result.volatile_constraints.requires_in_stock = True
        return result
