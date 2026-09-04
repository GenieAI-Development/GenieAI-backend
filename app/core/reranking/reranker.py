from __future__ import annotations

import json

from app.integrations.llm.reliable_executor import ReliableLLMExecutor
from app.schemas.internal import (
    QueryUnderstanding,
    RerankOutput,
    RerankedCandidate,
    VerifiedCandidate,
)


class SemanticReranker:
    def __init__(self, executor: ReliableLLMExecutor) -> None:
        self.executor = executor

    async def rerank(
        self,
        understanding: QueryUnderstanding,
        candidates: list[VerifiedCandidate],
    ) -> list[RerankedCandidate]:
        if not candidates:
            return []
        evidence = [
            {
                "product_id": item.product.product_id,
                "name": item.product.name,
                "description": item.product.description,
                "visual_interpretation": item.product.visual_interpretation,
                "category": item.category,
                "vendor": item.product.vendor,
                "live_price_lkr": item.live_price_lkr,
                "weight_kg": item.product.weight_kg,
                "rrf_score": item.retrieval.rrf_score,
            }
            for item in candidates
        ]
        expected = {item.product.product_id for item in candidates}

        def validate_candidate_set(value: RerankOutput) -> RerankOutput:
            returned = [decision.product_id for decision in value.decisions]
            if set(returned) != expected or len(returned) != len(expected):
                raise ValueError("reranker must return exactly one decision per candidate")
            return value

        output = await self.executor.execute(
            system_prompt=(
                "Rerank all candidates against the same original query. Mandatory semantic "
                "requirements and exclusions determine eligibility. Never invent evidence. "
                "Return one decision for every supplied product_id, with a concise grounded reason."
            ),
            user_prompt=json.dumps(
                {
                    "original_query": understanding.original_query,
                    "mandatory_semantic_requirements": understanding.mandatory_semantic_requirements,
                    "mandatory_semantic_exclusions": understanding.mandatory_semantic_exclusions,
                    "candidates": evidence,
                }
            ),
            response_model=RerankOutput,
            validator=validate_candidate_set,
        )
        by_id = {item.product.product_id: item for item in candidates}
        ranked = [
            RerankedCandidate(
                verified=by_id[decision.product_id],
                relevance_score=decision.relevance_score,
                reason=decision.reason,
            )
            for decision in output.decisions
            if decision.eligible
            and not decision.semantic_requirement_failures
            and not decision.semantic_exclusion_violations
        ]
        return sorted(ranked, key=lambda item: (-item.relevance_score, item.verified.product.product_id))
