import pytest

from app.orchestration.decision_agent_supervisor import DecisionAgentError, DecisionAgentSupervisor
from app.schemas.internal import CategoryScope, QueryUnderstanding, RetrievalPlan, StableConstraints


class QueryAgent:
    def __init__(self, original_query: str) -> None:
        self.original_query = original_query

    async def understand(self, message, request_type, previous_state):
        return QueryUnderstanding(
            original_query=self.original_query,
            category_scope=CategoryScope(
                mode="single_category", categories=["cakes"], user_explicit=True
            ),
        )


class PlanningAgent:
    def __init__(self, category="cakes", query="rose cake") -> None:
        self.category = category
        self.query = query

    async def plan(self, understanding, available_categories):
        return [
            RetrievalPlan(
                category=self.category,
                query=self.query,
                candidate_limit=20,
                stable_filters=StableConstraints(),
                required=True,
            )
        ]


@pytest.mark.asyncio
async def test_supervisor_preserves_typed_agent_handoff():
    supervisor = DecisionAgentSupervisor(QueryAgent("rose cake"), PlanningAgent())

    understanding = await supervisor.understand("rose cake", "product_recommendation")
    plans = await supervisor.plan(understanding, ["cakes"])

    assert understanding.original_query == "rose cake"
    assert plans[0].category == "cakes"


@pytest.mark.asyncio
async def test_supervisor_rejects_query_agent_that_changes_original_query():
    supervisor = DecisionAgentSupervisor(QueryAgent("changed"), PlanningAgent())

    with pytest.raises(DecisionAgentError, match="query understanding agent failed"):
        await supervisor.understand("rose cake", "product_recommendation")


@pytest.mark.asyncio
async def test_supervisor_rejects_invalid_planning_handoff():
    supervisor = DecisionAgentSupervisor(
        QueryAgent("rose cake"), PlanningAgent(category="flowers")
    )
    understanding = await supervisor.understand("rose cake", "product_recommendation")

    with pytest.raises(DecisionAgentError, match="recommendation planning agent failed"):
        await supervisor.plan(understanding, ["cakes"])
