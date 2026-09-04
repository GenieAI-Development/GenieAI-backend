import pytest

from app.core.planning.recommendation_planner import RecommendationPlanner
from app.optimizers.gift_box_optimizer import GiftBoxOptimizer
from app.orchestration.recommendation_orchestrator import RecommendationOrchestrator
from app.repositories.catalogue_repository import JsonCatalogueRepository
from app.schemas.catalogue import CategoryCatalogue, CatalogueProduct
from app.schemas.internal import (
    CategoryScope,
    QueryUnderstanding,
    RerankedCandidate,
    RetrievalHit,
    VerifiedCandidate,
)
from app.schemas.recommendation import RecommendationRequest
from app.sessions.store import InMemorySessionStore
from app.workflows.gift_box.context_resolver import GiftBoxContextResolver
from app.workflows.gift_box.workflow import GiftBoxWorkflow
from app.workflows.smart_shopping.workflow import SmartShoppingWorkflow


class NoopExecutor:
    async def execute(self, **kwargs):
        raise AssertionError("explicit category planning must be deterministic")


class QueryService:
    async def understand(self, message, request_type, previous_state):
        return QueryUnderstanding(
            original_query=message,
            category_scope=CategoryScope(
                mode="single_category", categories=["cakes"], user_explicit=True
            ),
        )


class Retriever:
    def __init__(self, fail=False):
        self.fail = fail

    async def retrieve(self, plan):
        if self.fail:
            raise RuntimeError("retrieval unavailable")
        return [RetrievalHit(product_id="C1", category="cakes", rrf_score=0.1)]


class Verifier:
    def __init__(self, product):
        self.product = product

    async def verify(self, hits, constraints):
        return [
            VerifiedCandidate(
                product=self.product,
                category="cakes",
                live_price_lkr=5000,
                image_url="https://example.test/cake.jpg",
                retrieval=hits[0],
            )
        ]


class Reranker:
    async def rerank(self, understanding, candidates):
        return [
            RerankedCandidate(verified=item, relevance_score=0.95, reason="Matches the rose theme.")
            for item in candidates
        ]


class Kapruka:
    async def validate_delivery(self, city, delivery_date):
        return True


def make_orchestrator(tmp_path):
    repository = JsonCatalogueRepository(tmp_path)
    product = CatalogueProduct(
        product_id="C1",
        name="Rose Cake",
        description="A rose-decorated cake",
        vendor="Vendor",
        is_active=True,
    )
    repository.save_category("cakes", CategoryCatalogue(category="cakes", products=[product]))
    sessions = InMemorySessionStore()
    orchestrator = RecommendationOrchestrator(
        sessions=sessions,
        repository=repository,
        query_understanding=QueryService(),
        gift_box_context=GiftBoxContextResolver(),
        planner=RecommendationPlanner(NoopExecutor()),
        retriever=Retriever(),
        verifier=Verifier(product),
        reranker=Reranker(),
        kapruka=Kapruka(),
        smart_shopping=SmartShoppingWorkflow(),
        gift_box=GiftBoxWorkflow(GiftBoxOptimizer()),
    )
    return orchestrator, sessions


@pytest.mark.asyncio
async def test_smart_shopping_end_to_end_generates_session_and_live_card(tmp_path):
    orchestrator, _ = make_orchestrator(tmp_path)
    response = await orchestrator.execute(
        RecommendationRequest(request_type="product_recommendation", message="romantic rose cake")
    )
    assert response.response_type == "limited_results"
    assert response.result_count == 1
    assert response.products[0].price_lkr == 5000
    assert response.products[0].image_url == "https://example.test/cake.jpg"
    assert response.request_id.startswith("req_")
    assert response.session_id


@pytest.mark.asyncio
async def test_failed_followup_does_not_corrupt_session(tmp_path):
    orchestrator, sessions = make_orchestrator(tmp_path)
    first = await orchestrator.execute(
        RecommendationRequest(request_type="product_recommendation", message="romantic cake")
    )
    before = await sessions.get(first.session_id)
    orchestrator.retriever = Retriever(fail=True)
    second = await orchestrator.execute(
        RecommendationRequest(
            request_type="product_recommendation",
            session_id=first.session_id,
            message="show another romantic cake",
        )
    )
    after = await sessions.get(first.session_id)
    assert second.response_type == "temporary_unavailable"
    assert before == after


@pytest.mark.asyncio
async def test_gift_box_end_to_end_uses_deterministic_optimizer(tmp_path):
    orchestrator, _ = make_orchestrator(tmp_path)
    response = await orchestrator.execute(
        RecommendationRequest(
            request_type="gift_box",
            message="Exactly 1 item for my girlfriend under Rs. 6,000",
            workflow_context={"theme": "romantic"},
        )
    )
    assert response.response_type == "recommendation"
    assert response.bundle.item_count == 1
    assert response.bundle.total_price_lkr == 5000

