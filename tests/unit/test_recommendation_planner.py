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


@pytest.mark.asyncio
async def test_chocolate_cake_selects_cakes_not_chocolates():
    understanding = QueryUnderstanding(
        original_query="I need a chocolate cake under Rs. 7000",
        category_scope=CategoryScope(
            mode="single_category",
            categories=["chocolate cake"],
            user_explicit=True,
        ),
    )

    plans = await RecommendationPlanner(NoopExecutor()).plan(
        understanding, ["cakes", "chocolates", "flowers"]
    )

    assert [plan.category for plan in plans] == ["cakes"]


@pytest.mark.asyncio
async def test_cake_with_chocolates_keeps_cake_as_the_product_type():
    understanding = QueryUnderstanding(
        original_query="I need a cake with chocolates",
        category_scope=CategoryScope(
            mode="single_category",
            categories=["cake with chocolates"],
            user_explicit=True,
        ),
    )

    plans = await RecommendationPlanner(NoopExecutor()).plan(
        understanding, ["cakes", "chocolates", "flowers"]
    )

    assert [plan.category for plan in plans] == ["cakes"]


@pytest.mark.asyncio
async def test_explicitly_joined_categories_select_multiple_categories():
    understanding = QueryUnderstanding(
        original_query="I need cakes and chocolates for a birthday",
        category_scope=CategoryScope(
            mode="multiple_categories",
            categories=["cakes", "chocolates"],
            user_explicit=True,
        ),
    )

    plans = await RecommendationPlanner(NoopExecutor()).plan(
        understanding, ["cakes", "chocolates", "flowers"]
    )

    assert [plan.category for plan in plans] == ["cakes", "chocolates"]
