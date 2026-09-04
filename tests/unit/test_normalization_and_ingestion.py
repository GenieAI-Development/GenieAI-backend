import pytest

from app.ingestion.product_ingestion import ProductIngestion
from app.ingestion.visual_interpretation_import import (
    UnknownInterpretationProductError,
    VisualInterpretationImporter,
)
from app.integrations.kapruka.normalizer import normalize_product, normalize_weight
from app.repositories.catalogue_repository import JsonCatalogueRepository
from app.schemas.admin import ProductImportRequest, VisualInterpretationImportRequest
from app.schemas.catalogue import CategoryCatalogue, CatalogueProduct


def mcp_product(product_id="P1", description="Weight: 2.77 Lbs (1.25 KG)"):
    return {
        "id": product_id,
        "name": "Rose Cake",
        "description": description,
        "price": {"amount": "5770"},
        "in_stock": True,
        "category": {"slug": "cakes"},
        "images": ["https://example.test/cake.jpg"],
        "attributes": {"vendor": "Kapruka Cakes", "weight": "2.77"},
    }


def test_mcp_product_maps_only_canonical_fields():
    item = normalize_product(mcp_product(), "cakes")
    assert item.product_id == "P1"
    assert item.weight_kg == 1.25
    assert item.price_snapshot_lkr == 5770
    assert "image_url" not in item.model_dump()


def test_weight_normalization_rules():
    assert normalize_weight("Net weight 1.5 KG", "9") == 1.5
    assert normalize_weight("Net weight 2.2 lbs") == pytest.approx(0.998)
    assert normalize_weight("Weight 2.77", "2.77") is None


class FakeKapruka:
    async def get_product(self, product_id):
        if product_id == "bad":
            raise RuntimeError("not found")
        return mcp_product(product_id)

    async def validate_delivery(self, city, delivery_date):
        return True


@pytest.mark.asyncio
async def test_failed_product_does_not_create_record(tmp_path):
    repository = JsonCatalogueRepository(tmp_path)
    result = await ProductIngestion(repository, FakeKapruka()).import_products(
        ProductImportRequest(category="cakes", product_ids=["P1", "bad", "P1"])
    )
    assert result.imported_count == 1
    assert result.failed_product_ids == ["bad"]
    assert [p.product_id for p in repository.load_category("cakes").products] == ["P1"]


def test_visual_import_rejects_unknown_and_preserves_catalogue(tmp_path):
    repository = JsonCatalogueRepository(tmp_path)
    repository.save_category(
        "cakes",
        CategoryCatalogue(
            category="cakes",
            products=[
                CatalogueProduct(
                    product_id="P1",
                    name="Cake",
                    description="Description",
                    vendor="Vendor",
                    is_active=True,
                )
            ],
        ),
    )
    importer = VisualInterpretationImporter(repository)
    request = VisualInterpretationImportRequest(
        category="cakes",
        items=[{"product_id": "missing", "visual_interpretation": "Red flowers"}],
    )
    with pytest.raises(UnknownInterpretationProductError):
        importer.import_items(request)
    assert repository.load_category("cakes").products[0].visual_interpretation is None


def test_visual_import_safe_default_skips_existing(tmp_path):
    repository = JsonCatalogueRepository(tmp_path)
    repository.save_category(
        "cakes",
        CategoryCatalogue(
            category="cakes",
            products=[
                CatalogueProduct(
                    product_id="P1",
                    name="Cake",
                    description="Description",
                    vendor="Vendor",
                    is_active=True,
                    visual_interpretation="Original",
                )
            ],
        ),
    )
    result = VisualInterpretationImporter(repository).import_items(
        VisualInterpretationImportRequest(
            category="cakes",
            items=[{"product_id": "P1", "visual_interpretation": "Replacement"}],
        )
    )
    assert result.skipped_count == 1
    assert repository.load_category("cakes").products[0].visual_interpretation == "Original"

