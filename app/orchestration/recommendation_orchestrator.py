from __future__ import annotations

from uuid import UUID

from app.integrations.llm.reliable_executor import LLMDecisionError
from app.observability.tracing import RequestTrace, new_request_id
from app.observability.logging import log_event
from app.schemas.recommendation import (
    ClarificationResponse,
    DeliveryUnavailableResponse,
    RecommendationRequest,
    RuntimeResponse,
    TemporaryUnavailableResponse,
    WorkflowMismatchResponse,
)
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

        if understanding.workflow_mismatch.detected:
            suggested = understanding.workflow_mismatch.suggested_workflow
            if suggested is None:
                suggested = "gift_box" if request.request_type == "product_recommendation" else "product_recommendation"
            response = WorkflowMismatchResponse(
                request_id=request_id,
                session_id=session.session_id,
                request_type=request.request_type,
                response_type="workflow_mismatch",
                message="This request is better suited to the other GenieAI shopping workflow.",
                suggested_workflow=suggested,
            )
            trace.finish("workflow_mismatch", 0)
            return response
        if understanding.clarification.required:
            if request.request_type == "product_recommendation":
                session.product_search_state = ProductSearchState(
                    query_understanding=understanding.model_dump(mode="json")
                )
            else:
                session.gift_box_state = gift_state
            await self.sessions.save(session)
            response = ClarificationResponse(
                request_id=request_id,
                session_id=session.session_id,
                request_type=request.request_type,
                response_type="clarification",
                message=understanding.clarification.reason or "Could you provide a little more detail?",
                missing_fields=understanding.clarification.missing_information,
            )
            trace.finish("clarification", 0)
            return response
        if understanding.delivery_request is not None:
            try:
                with trace.stage("delivery_validation"):
                    available = await self.kapruka.validate_delivery(
                        understanding.delivery_request.city,
                        understanding.delivery_request.delivery_date.isoformat(),
                    )
            except Exception:
                response = self._temporary(
                    request_id,
                    session,
                    request.request_type,
                    "I couldn't confirm delivery right now. Please try again.",
                )
                trace.finish("temporary_unavailable", 0, "DELIVERY_VALIDATION_UNAVAILABLE")
                return response
            if not available:
                response = DeliveryUnavailableResponse(
                    request_id=request_id,
                    session_id=session.session_id,
                    request_type=request.request_type,
                    response_type="delivery_unavailable",
                    message="Delivery isn't available for the location or date you selected.",
                )
                trace.finish("delivery_unavailable", 0)
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
        attempted_ids: set[str] = set()
        ranked = []
        retrieval_ever_succeeded = False
        try:
            for depth in list(dict.fromkeys([self.fused_top_k, 40, 60])):
                new_hits = []
                for plan in plans:
                    expanded = plan.model_copy(update={"candidate_limit": depth})
                    try:
                        with trace.stage("hybrid_retrieval"):
                            hits = await self.retriever.retrieve(expanded)
                        retrieval_ever_succeeded = True
                    except Exception:
                        if plan.required:
                            raise
                        continue
                    for hit in hits:
                        if hit.product_id in attempted_ids:
                            continue
                        attempted_ids.add(hit.product_id)
                        new_hits.append(hit)
                if not new_hits:
                    break
                with trace.stage("live_verification"):
                    verified = await self.verifier.verify(
                        new_hits, understanding.volatile_constraints
                    )
                for item in verified:
                    all_verified[item.product.product_id] = item
                with trace.stage("reranking"):
                    ranked = await self.reranker.rerank(
                        understanding, list(all_verified.values())
                    )
                log_event(
                    "reranking_outcome",
                    verified_candidate_count=len(all_verified),
                    semantic_eligible_count=len(ranked),
                    expansion_depth=depth,
                )
                target = (
                    gift_state.item_count or 4
                    if request.request_type == "gift_box"
                    else self.smart_target
                )
                if len(ranked) >= target:
                    break
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
            response = self.smart_shopping.build_response(
                request_id=request_id, session_id=session.session_id, candidates=ranked
            )
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
