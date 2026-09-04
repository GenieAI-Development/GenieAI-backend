import pytest

from app.core.planning.recommendation_planner import RecommendationPlanner
from app.schemas.internal import CategoryScope, QueryUnderstanding


class NoopExecutor:
    async def execute(self, **kwargs):
        raise AssertionError("a clear catalogue-category match must be deterministic")


@pytest.mark.asyncio
async def test_explicit_category_phrase_maps_to_real_catalogue_category():
    understanding = QueryUnderstanding(
        original_query="I need a romantic birthday cake under Rs. 7000",
        category_scope=CategoryScope(
            mode="single_category",
            categories=["birthday cake"],
            user_explicit=True,
        ),
    )

    plans = await RecommendationPlanner(NoopExecutor()).plan(
        understanding, ["cakes"]
    )

    assert [plan.category for plan in plans] == ["cakes"]
    assert plans[0].required is True
