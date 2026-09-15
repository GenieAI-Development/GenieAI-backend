from __future__ import annotations

import time
from typing import Protocol

from app.observability.logging import log_event
from app.schemas.internal import QueryUnderstanding, RetrievalPlan


class DecisionAgentError(RuntimeError):
    """A supervised agent failed or violated its handoff contract."""


class QueryAgent(Protocol):
    async def understand(
        self,
        message: str,
        request_type: str,
        previous_state: dict[str, object] | None = None,
    ) -> QueryUnderstanding: ...


class RetrievalPlanningAgent(Protocol):
    async def plan(
        self,
        understanding: QueryUnderstanding,
        available_categories: list[str],
    ) -> list[RetrievalPlan]: ...


class DecisionAgentSupervisor:
    """Runs and validates the two LLM decision agents in the fixed pipeline."""

    def __init__(self, query_agent: QueryAgent, planning_agent: RetrievalPlanningAgent) -> None:
        self.query_agent = query_agent
        self.planning_agent = planning_agent

    async def understand(
        self,
        message: str,
        request_type: str,
        previous_state: dict[str, object] | None = None,
    ) -> QueryUnderstanding:
        started = time.perf_counter()
        try:
            understanding = await self.query_agent.understand(
                message, request_type, previous_state
            )
            understanding = QueryUnderstanding.model_validate(understanding)
            if understanding.original_query != message:
                raise ValueError("query agent changed the original query")
        except Exception as exc:
            self._log_outcome("query_understanding", started, exc)
            if isinstance(exc, DecisionAgentError):
                raise
            raise DecisionAgentError("query understanding agent failed") from exc
        self._log_outcome("query_understanding", started)
        return understanding

    async def plan(
        self,
        understanding: QueryUnderstanding,
        available_categories: list[str],
    ) -> list[RetrievalPlan]:
        started = time.perf_counter()
        try:
            raw_plans = await self.planning_agent.plan(understanding, available_categories)
            plans = [RetrievalPlan.model_validate(plan) for plan in raw_plans]
            allowed = set(available_categories)
            for plan in plans:
                if plan.category not in allowed:
                    raise ValueError("planning agent selected an unavailable category")
                if plan.query != understanding.original_query:
                    raise ValueError("planning agent did not preserve the original query")
        except Exception as exc:
            self._log_outcome("recommendation_planning", started, exc)
            if isinstance(exc, DecisionAgentError):
                raise
            raise DecisionAgentError("recommendation planning agent failed") from exc
        self._log_outcome("recommendation_planning", started)
        return plans

    @staticmethod
    def _log_outcome(agent: str, started: float, error: Exception | None = None) -> None:
        log_event(
            "decision_agent_outcome",
            agent=agent,
            status="failed" if error is not None else "completed",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            failure_type=type(error).__name__ if error is not None else None,
        )
