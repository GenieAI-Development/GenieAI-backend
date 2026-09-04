from __future__ import annotations

from app.repositories.catalogue_repository import CatalogueRepository
from app.schemas.admin import (
    VisualInterpretationImportRequest,
    VisualInterpretationImportResponse,
)
from app.schemas.catalogue import CategoryCatalogue


class UnknownInterpretationProductError(ValueError):
    """An interpretation refers to a product outside the requested catalogue."""


class VisualInterpretationImporter:
    def __init__(self, repository: CatalogueRepository) -> None:
        self.repository = repository

    def import_items(
        self, request: VisualInterpretationImportRequest
    ) -> VisualInterpretationImportResponse:
        catalogue = self.repository.load_category(request.category)
        products = {product.product_id: product.model_copy(deep=True) for product in catalogue.products}
        unknown = sorted({item.product_id for item in request.items} - products.keys())
        if unknown:
            raise UnknownInterpretationProductError(
                f"unknown product IDs for {request.category}: {', '.join(unknown)}"
            )
        updated = 0
        skipped = 0
        for item in request.items:
            product = products[item.product_id]
            if product.visual_interpretation and not request.replace_existing:
                skipped += 1
                continue
            product.visual_interpretation = item.visual_interpretation
            product.visual_interpretation_model = request.model_name
            updated += 1
        if updated:
            self.repository.save_category(
                request.category,
                CategoryCatalogue(category=request.category, products=list(products.values())),
            )
        return VisualInterpretationImportResponse(
            category=request.category, updated_count=updated, skipped_count=skipped
        )
