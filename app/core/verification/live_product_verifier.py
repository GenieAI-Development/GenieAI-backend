from __future__ import annotations

import asyncio
from contextlib import nullcontext

from app.integrations.kapruka.client import KaprukaClient
from app.integrations.kapruka.normalizer import extract_live_product
from app.repositories.catalogue_repository import CatalogueRepository
from app.observability.logging import log_event
from app.schemas.internal import RetrievalHit, VerifiedCandidate, VolatileConstraints


class LiveVerificationUnavailableError(RuntimeError):
    """Live commerce verification is broadly unavailable."""


class LiveProductVerifier:
    def __init__(
        self,
        kapruka: KaprukaClient,
        repository: CatalogueRepository,
        concurrency: int = 8,
        broad_failure_ratio: float = 0.5,
    ) -> None:
        self.kapruka = kapruka
        self.repository = repository
        self.concurrency = concurrency
        self.broad_failure_ratio = broad_failure_ratio

    async def verify(
        self, hits: list[RetrievalHit], constraints: VolatileConstraints
    ) -> list[VerifiedCandidate]:
        semaphore = asyncio.Semaphore(self.concurrency)

        async def one(hit: RetrievalHit):
            async with semaphore:
                try:
                    payload = await self.kapruka.get_product(hit.product_id)
                    price, in_stock, image_url = extract_live_product(payload)
                    return hit, price, in_stock, image_url, None
                except Exception as exc:
                    return hit, None, None, None, exc

        scope_factory = getattr(self.kapruka, "session_scope", None)
        scope = scope_factory() if callable(scope_factory) else nullcontext()
        results = []
        try:
            async with scope:
                results = await asyncio.gather(*(one(hit) for hit in hits))
        except Exception as exc:
            if not results:
                raise
            log_event(
                "kapruka_mcp_session_close_failed",
                failure_type=type(exc).__name__,
            )
        failures = sum(result[4] is not None for result in results)
        successes = len(results) - failures
        log_event(
            "live_verification_summary",
            attempted=len(results),
            successful_responses=successes,
            failed_responses=failures,
        )
        if results and (
            successes == 0
            or (failures / len(results) >= self.broad_failure_ratio and failures > successes)
        ):
            raise LiveVerificationUnavailableError("live product verification broadly failed")

        catalogues = {}
        verified: list[VerifiedCandidate] = []
        for hit, price, in_stock, image_url, error in results:
            if error is not None or not in_stock or image_url is None or price is None:
                continue
            if constraints.min_price is not None and price < constraints.min_price:
                continue
            if constraints.max_price is not None and price > constraints.max_price:
                continue
            if hit.category not in catalogues:
                catalogue = self.repository.load_category(hit.category)
                catalogues[hit.category] = {item.product_id: item for item in catalogue.products}
            product = catalogues[hit.category].get(hit.product_id)
            if product is None or not product.is_active:
                continue
            verified.append(
                VerifiedCandidate(
                    product=product,
                    category=hit.category,
                    live_price_lkr=price,
                    image_url=image_url,
                    retrieval=hit,
                )
            )
        return verified
