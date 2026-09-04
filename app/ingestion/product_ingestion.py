from __future__ import annotations

import asyncio

from app.integrations.kapruka.client import KaprukaClient
from app.integrations.kapruka.normalizer import normalize_product
from app.observability.logging import log_event
from app.repositories.catalogue_repository import (
    CatalogueNotFoundError,
    CatalogueRepository,
)
from app.schemas.admin import ProductImportRequest, ProductImportResponse
from app.schemas.catalogue import CategoryCatalogue


class ProductIngestion:
    def __init__(
        self,
        repository: CatalogueRepository,
        kapruka: KaprukaClient,
        concurrency: int = 8,
    ) -> None:
        self.repository = repository
        self.kapruka = kapruka
        self.concurrency = concurrency

    async def import_products(self, request: ProductImportRequest) -> ProductImportResponse:
        try:
            existing = self.repository.load_category(request.category)
        except CatalogueNotFoundError:
            existing = CategoryCatalogue(category=request.category, products=[])
        semaphore = asyncio.Semaphore(self.concurrency)

        async def fetch(product_id: str):
            async with semaphore:
                try:
                    payload = await self.kapruka.get_product(product_id)
                    product = normalize_product(payload, request.category)
                    if product.product_id != product_id:
                        raise ValueError("MCP product ID mismatch")
                    return product_id, product
                except Exception as exc:
                    log_event(
                        "product_ingestion_failed",
                        category=request.category,
                        product_id=product_id,
                        failure_type=type(exc).__name__,
                    )
                    return product_id, None

        results = await asyncio.gather(*(fetch(product_id) for product_id in request.product_ids))
        products = {item.product_id: item for item in existing.products}
        failed: list[str] = []
        imported = 0
        for product_id, product in results:
            if product is None:
                failed.append(product_id)
                continue
            old = products.get(product_id)
            if old is not None:
                product.visual_interpretation = old.visual_interpretation
                product.visual_interpretation_model = old.visual_interpretation_model
            products[product_id] = product
            imported += 1
        if imported:
            self.repository.save_category(
                request.category,
                CategoryCatalogue(category=request.category, products=list(products.values())),
            )
        return ProductImportResponse(
            category=request.category,
            imported_count=imported,
            failed_product_ids=failed,
        )
