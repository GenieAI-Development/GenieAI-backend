from __future__ import annotations

from app.schemas.internal import RetrievalHit
from app.observability.logging import log_event


def reciprocal_rank_fusion(
    category: str,
    dense: list[tuple[str, float]],
    bm25: list[tuple[str, float]],
    limit: int,
    rrf_k: int = 60,
) -> list[RetrievalHit]:
    evidence: dict[str, dict[str, int | float | None]] = {}
    for name, results in (("dense_rank", dense), ("bm25_rank", bm25)):
        for rank, (product_id, _) in enumerate(results, start=1):
            item = evidence.setdefault(
                product_id, {"dense_rank": None, "bm25_rank": None, "score": 0.0}
            )
            if item[name] is None:
                item[name] = rank
                item["score"] = float(item["score"]) + 1.0 / (rrf_k + rank)
    ordered = sorted(evidence.items(), key=lambda item: (-float(item[1]["score"]), item[0]))
    return [
        RetrievalHit(
            product_id=product_id,
            category=category,
            dense_rank=data["dense_rank"],
            bm25_rank=data["bm25_rank"],
            rrf_score=float(data["score"]),
        )
        for product_id, data in ordered[:limit]
    ]


class RetrievalUnavailableError(RuntimeError):
    """Both retrieval mechanisms failed for a category plan."""


class HybridRetriever:
    def __init__(self, dense, bm25, rrf_k: int = 60) -> None:
        self.dense = dense
        self.bm25 = bm25
        self.rrf_k = rrf_k

    async def retrieve(self, plan):
        dense_results = None
        bm25_results = None
        dense_error = bm25_error = None
        try:
            dense_results = await self.dense.retrieve(plan)
        except Exception as exc:
            dense_error = exc
        try:
            bm25_results = await self.bm25.retrieve(plan)
        except Exception as exc:
            bm25_error = exc
        if dense_results is None and bm25_results is None:
            raise RetrievalUnavailableError("both dense and BM25 retrieval failed") from (
                dense_error or bm25_error
            )
        if dense_results is None or bm25_results is None:
            log_event(
                "retrieval_degraded",
                category=plan.category,
                dense_available=dense_results is not None,
                bm25_available=bm25_results is not None,
            )
        fused = reciprocal_rank_fusion(
            plan.category,
            dense_results or [],
            bm25_results or [],
            plan.candidate_limit,
            self.rrf_k,
        )
        log_event(
            "retrieval_counts",
            category=plan.category,
            dense_candidate_count=len(dense_results or []),
            bm25_candidate_count=len(bm25_results or []),
            rrf_candidate_count=len(fused),
        )
        return fused
