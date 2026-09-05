from __future__ import annotations

from uuid import UUID

from app.integrations.llm.reliable_executor import LLMDecisionError
from app.observability.tracing import RequestTrace, new_request_id
from app.observability.logging import log_event
from app.schemas.recommendation import (
    ClarificationResponse,
    ProductCard,
    RecommendationRequest,
    RuntimeResponse,
    SmartShoppingResponse,
    TemporaryUnavailableResponse,
)
from app.schemas.internal import RerankedCandidate
from app.sessions.models import RecommendationSession, ProductSearchState


_CONTEXT_REFERENCES = ("cheaper ones", "more like", "first one", "second one", "number ")


class RecommendationOrchestrator:
    def __init__(
        self,
        *,
        sessions,
        repository,
        query_understanding,
        gift_box_context,
        planner,
        retriever,
        verifier,
        reranker,
        kapruka,
        smart_shopping,
        gift_box,
        fused_top_k: int = 20,
        smart_target: int = 12,
    ) -> None:
        self.sessions = sessions
        self.repository = repository
        self.query_understanding = query_understanding
        self.gift_box_context = gift_box_context
        self.planner = planner
        self.retriever = retriever
        self.verifier = verifier
        self.reranker = reranker
        self.kapruka = kapruka
        self.smart_shopping = smart_shopping
        self.gift_box = gift_box
        self.fused_top_k = fused_top_k
        self.smart_target = smart_target

    async def _session_for(self, supplied: UUID | None, message: str):
        if supplied is None:
            return await self.sessions.create(), False
        existing = await self.sessions.get(str(supplied))
        if existing is not None:
            return existing, False
        created = await self.sessions.create()
        dependent = any(marker in message.casefold() for marker in _CONTEXT_REFERENCES)
        return created, dependent

    @staticmethod
    def _temporary(request_id, session, request_type, message):
        return TemporaryUnavailableResponse(
            request_id=request_id,
            session_id=session.session_id,
            request_type=request_type,
            response_type="temporary_unavailable",
            message=message,
        )

    def _direct_smart_shopping_response(
        self, request_id: str, session_id: str, candidates: list[RerankedCandidate]
    ) -> SmartShoppingResponse:
        selected = candidates[: self.smart_target]
        products = [
            ProductCard(
                product_id=item.verified.product.product_id,
                name=item.verified.cached_name or item.verified.product.name,
                price_lkr=item.verified.live_price_lkr,
                image_url=item.verified.image_url,
                vendor=item.verified.cached_vendor or item.verified.product.vendor,
                description=item.verified.cached_description,
            )
            for item in selected
        ]
        response_type = "recommendation" if len(products) >= self.smart_target else "limited_results"
        message = (
            "I found the strongest available matches for your request."
            if products
            else "I couldn't find an available product that meets all of your requirements."
        )
        return SmartShoppingResponse(
            request_id=request_id,
            session_id=session_id,
            request_type="product_recommendation",
            response_type=response_type,
            message=message,
            result_count=len(products),
            products=products,
        )

    async def execute(self, request: RecommendationRequest) -> RuntimeResponse:
        request_id = new_request_id()
        session, missing_context = await self._session_for(request.session_id, request.message)
        trace = RequestTrace(request_id, session.session_id, request.request_type)
        if missing_context:
            response = ClarificationResponse(
                request_id=request_id,
                session_id=session.session_id,
                request_type=request.request_type,
                response_type="clarification",
                message="I no longer have the earlier recommendation context. What would you like me to find?",
                missing_fields=["category"],
            )
            trace.finish("clarification", 0)
            return response

        gift_state = session.gift_box_state
        if request.request_type == "gift_box":
            with trace.stage("gift_box_context_resolution"):
                gift_state = self.gift_box_context.resolve(
                    request.message, request.workflow_context, session.gift_box_state
                )
            missing = self.gift_box_context.missing_fields(gift_state)
            if missing:
                session.gift_box_state = gift_state
                await self.sessions.save(session)
                response = ClarificationResponse(
                    request_id=request_id,
                    session_id=session.session_id,
                    request_type="gift_box",
                    response_type="clarification",
                    message="Who is the gift for or what theme should it have, and what budget should I use?",
                    missing_fields=missing,
                )
                trace.finish("clarification", 0)
                return response

        previous = (
            session.product_search_state.query_understanding
            if request.request_type == "product_recommendation"
            else {}
        )
        try:
            with trace.stage("query_understanding"):
                understanding = await self.query_understanding.understand(
                    request.message, request.request_type, previous
                )
        except LLMDecisionError:
            response = self._temporary(
                request_id,
                session,
                request.request_type,
                "I couldn't interpret the request reliably right now. Please try again.",
            )
            trace.finish("temporary_unavailable", 0, "LLM_DECISION_FAILURE")
            return response

        try:
            categories = self.repository.list_categories()
        except Exception:
            response = self._temporary(
                request_id,
                session,
                request.request_type,
                "The product catalogue is temporarily unavailable.",
            )
            trace.finish("temporary_unavailable", 0, "CATALOGUE_FAILURE")
            return response
        try:
            with trace.stage("recommendation_planning"):
                plans = await self.planner.plan(understanding, categories)
        except LLMDecisionError:
            response = self._temporary(
                request_id, session, request.request_type, "I couldn't plan the search reliably right now."
            )
            trace.finish("temporary_unavailable", 0, "LLM_DECISION_FAILURE")
            return response

        all_verified = {}
        ranked: list[RerankedCandidate] = []
        retrieval_ever_succeeded = False
        try:
            for plan in plans:
                expanded = plan.model_copy(update={"candidate_limit": 60})
                try:
                    with trace.stage("hybrid_retrieval"):
                        hits = await self.retriever.retrieve(expanded)
                    retrieval_ever_succeeded = True
                except Exception:
                    if plan.required:
                        raise
                    continue
                with trace.stage("cached_product_verification"):
                    verified = await self.verifier.verify(hits, understanding.volatile_constraints)
                for item in verified:
                    all_verified[item.product.product_id] = item
            ranked = sorted(
                (
                    RerankedCandidate(
                        verified=item,
                        relevance_score=item.retrieval.rrf_score,
                        reason="Matched your search and passed cached price and availability checks.",
                    )
                    for item in all_verified.values()
                ),
                key=lambda item: (-item.relevance_score, item.verified.product.product_id),
            )
            log_event(
                "direct_retrieval_outcome",
                retrieved_candidate_limit=60,
                verified_candidate_count=len(all_verified),
            )
        except Exception as exc:
            category = (
                "RERANKER_FAILURE"
                if isinstance(exc, (LLMDecisionError, ValueError))
                else "RETRIEVAL_OR_VERIFICATION_FAILURE"
            )
            cause = exc.__cause__
            log_event(
                "recommendation_pipeline_failed",
                failure_category=category,
                failure_type=type(exc).__name__,
                failure_message=str(exc),
                cause_type=type(cause).__name__ if cause is not None else None,
                cause_message=str(cause) if cause is not None else None,
            )
            response = self._temporary(
                request_id,
                session,
                request.request_type,
                "I couldn't confirm suitable products right now. Please try again shortly.",
            )
            trace.finish("temporary_unavailable", 0, category)
            return response
        if plans and not retrieval_ever_succeeded:
            response = self._temporary(
                request_id, session, request.request_type, "Product search is temporarily unavailable."
            )
            trace.finish("temporary_unavailable", 0, "RETRIEVAL_FAILURE")
            return response

        if request.request_type == "product_recommendation":
            response = self._direct_smart_shopping_response(request_id, session.session_id, ranked)
            session.product_search_state = ProductSearchState(
                query_understanding=understanding.model_dump(mode="json"),
                previous_product_ids=[item.product_id for item in response.products],
            )
            result_count = response.result_count
        else:
            required = set(understanding.category_scope.categories) if understanding.category_scope.user_explicit else set()
            response = self.gift_box.build_response(
                request_id=request_id,
                session_id=session.session_id,
                state=gift_state,
                candidates=ranked,
                required_categories=required,
            )
            session.gift_box_state = gift_state
            result_count = response.bundle.item_count if hasattr(response, "bundle") else 0
        await self.sessions.save(session)
        trace.finish(response.response_type, result_count)
        return response
