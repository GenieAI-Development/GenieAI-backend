from contextlib import asynccontextmanager

import pytest

from app.core.retrieval.rrf_fusion import HybridRetriever, RetrievalUnavailableError, reciprocal_rank_fusion
from app.core.verification.live_product_verifier import (
    LiveProductVerifier,
    LiveVerificationUnavailableError,
)
from app.integrations.llm.reliable_executor import LLMDecisionError, ReliableLLMExecutor
from app.optimizers.gift_box_optimizer import GiftBoxOptimizer
from app.repositories.catalogue_repository import JsonCatalogueRepository
from app.schemas.catalogue import CategoryCatalogue, CatalogueProduct
from app.schemas.gift_box import GiftBoxState
from app.schemas.internal import (
    CategoryScope,
    QueryUnderstanding,
    RerankDecision,
    RerankOutput,
    RerankedCandidate,
    RetrievalHit,
    RetrievalPlan,
    StableConstraints,
    VerifiedCandidate,
    VolatileConstraints,
)


def test_rrf_deduplicates_and_preserves_ranks():
    hits = reciprocal_rank_fusion("cakes", [("A", 0.9), ("B", 0.8)], [("B", 4), ("C", 3)], 5)
    assert [hit.product_id for hit in hits] == ["B", "A", "C"]
    assert hits[0].dense_rank == 2 and hits[0].bm25_rank == 1


class Retriever:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    async def retrieve(self, plan):
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_hybrid_degrades_to_single_retriever_and_both_fail():
    plan = RetrievalPlan(
        category="cakes", query="rose", candidate_limit=20, stable_filters=StableConstraints()
    )
    hybrid = HybridRetriever(Retriever(error=RuntimeError()), Retriever([("A", 1.0)]))
    assert (await hybrid.retrieve(plan))[0].product_id == "A"
    with pytest.raises(RetrievalUnavailableError):
        await HybridRetriever(Retriever(error=RuntimeError()), Retriever(error=RuntimeError())).retrieve(plan)


class SequenceLLM:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.models = []

    async def complete(self, **kwargs):
        self.models.append(kwargs["model"])
        result = next(self.outcomes)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.mark.asyncio
async def test_reliable_llm_retries_then_falls_back():
    valid = RerankOutput(
        decisions=[RerankDecision(product_id="A", eligible=True, relevance_score=0.9, reason="Match")]
    )
    client = SequenceLLM([RuntimeError(), RuntimeError(), valid])
    executor = ReliableLLMExecutor(client, "primary", ["fallback"], 2)
    assert await executor.execute(system_prompt="s", user_prompt="u", response_model=RerankOutput) == valid
    assert client.models == ["primary", "primary", "fallback"]


@pytest.mark.asyncio
async def test_reliable_llm_complete_failure():
    executor = ReliableLLMExecutor(SequenceLLM([RuntimeError(), RuntimeError()]), "p", ["f"], 1)
    with pytest.raises(LLMDecisionError):
        await executor.execute(system_prompt="s", user_prompt="u", response_model=RerankOutput)


@pytest.mark.asyncio
async def test_reliable_llm_retries_when_component_validator_rejects_output():
    invalid = RerankOutput(decisions=[])
    valid = RerankOutput(
        decisions=[RerankDecision(product_id="A", eligible=True, relevance_score=0.9, reason="Match")]
    )
    client = SequenceLLM([invalid, valid])
    executor = ReliableLLMExecutor(client, "primary", [], 2)

    def require_decision(value):
        if not value.decisions:
            raise ValueError("missing decisions")
        return value

    result = await executor.execute(
        system_prompt="s",
        user_prompt="u",
        response_model=RerankOutput,
        validator=require_decision,
    )
    assert result == valid


class FakeKapruka:
    def __init__(self, failures=None, stock=None):
        self.failures = failures or set()
        self.stock = stock or {}

    async def get_product(self, product_id):
        if product_id in self.failures:
            raise RuntimeError("MCP down")
        return {
            "price": {"amount": 5000 if product_id != "expensive" else 9000},
            "in_stock": self.stock.get(product_id, True),
            "images": [{"url": f"https://example.test/{product_id}.jpg"}],
        }


class ClosingErrorKapruka(FakeKapruka):
    @asynccontextmanager
    async def session_scope(self):
        yield
        raise RuntimeError("transport close failed")


def catalogue_product(product_id):
    return CatalogueProduct(
        product_id=product_id, name=product_id, description="Rose gift", vendor="Vendor", is_active=True
    )


def hit(product_id, category="cakes"):
    return RetrievalHit(product_id=product_id, category=category, rrf_score=0.1)


@pytest.mark.asyncio
async def test_live_verification_filters_stock_budget_and_individual_failure(tmp_path):
    repository = JsonCatalogueRepository(tmp_path)
    ids = ["ok", "oos", "expensive", "broken"]
    repository.save_category(
        "cakes", CategoryCatalogue(category="cakes", products=[catalogue_product(value) for value in ids])
    )
    verifier = LiveProductVerifier(
        FakeKapruka(failures={"broken"}, stock={"oos": False}), repository, broad_failure_ratio=0.75
    )
    result = await verifier.verify([hit(value) for value in ids], VolatileConstraints(max_price=7000))
    assert [item.product.product_id for item in result] == ["ok"]
    assert result[0].image_url.endswith("ok.jpg")


@pytest.mark.asyncio
async def test_live_verification_broad_failure_is_controlled(tmp_path):
    repository = JsonCatalogueRepository(tmp_path)
    repository.save_category(
        "cakes", CategoryCatalogue(category="cakes", products=[catalogue_product("A"), catalogue_product("B")])
    )
    verifier = LiveProductVerifier(FakeKapruka(failures={"A", "B"}), repository)
    with pytest.raises(LiveVerificationUnavailableError):
        await verifier.verify([hit("A"), hit("B")], VolatileConstraints())


@pytest.mark.asyncio
async def test_live_verification_keeps_results_when_session_close_fails(tmp_path):
    repository = JsonCatalogueRepository(tmp_path)
    repository.save_category(
        "cakes",
        CategoryCatalogue(category="cakes", products=[catalogue_product("A")]),
    )

    result = await LiveProductVerifier(ClosingErrorKapruka(), repository).verify(
        [hit("A")], VolatileConstraints()
    )

    assert [item.product.product_id for item in result] == ["A"]


def reranked(product_id, price, category, score):
    product = catalogue_product(product_id)
    verified = VerifiedCandidate(
        product=product,
        category=category,
        live_price_lkr=price,
        image_url="https://example.test/image.jpg",
        retrieval=hit(product_id, category),
    )
    return RerankedCandidate(verified=verified, relevance_score=score, reason="Good match")


def test_gift_box_optimizer_enforces_count_budget_and_required_category():
    candidates = [
        reranked("A", 4000, "cakes", 0.9),
        reranked("B", 5000, "flowers", 0.8),
        reranked("C", 9000, "chocolates", 1.0),
    ]
    solution = GiftBoxOptimizer().optimize(
        candidates,
        GiftBoxState(item_count=2, budget_min_lkr=8000, budget_max_lkr=10000),
        {"flowers"},
    )
    assert solution is not None
    assert len(solution.products) == 2
    assert solution.total_price_lkr == 9000
    assert {item.verified.category for item in solution.products} >= {"flowers"}


def test_gift_box_optimizer_no_solution_is_safe():
    result = GiftBoxOptimizer().optimize(
        [reranked("A", 5000, "cakes", 0.9)],
        GiftBoxState(item_count=2, budget_max_lkr=4000),
    )
    assert result is None
