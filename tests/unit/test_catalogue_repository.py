import json

import pytest
from pydantic import ValidationError

from app.repositories.catalogue_repository import (
    CatalogueValidationError,
    JsonCatalogueRepository,
)
from app.schemas.catalogue import CategoryCatalogue, CatalogueProduct


def product(**overrides: object) -> CatalogueProduct:
    values = {
        "product_id": "P1",
        "name": "Rose Cake",
        "description": "A floral cake",
        "vendor": "Kapruka Cakes",
        "is_active": True,
    }
    values.update(overrides)
    return CatalogueProduct.model_validate(values)


def test_valid_catalogue_round_trip(tmp_path):
    repository = JsonCatalogueRepository(tmp_path)
    catalogue = CategoryCatalogue(category="cakes", products=[product()])
    repository.save_category("cakes", catalogue)
    assert repository.load_category("cakes") == catalogue
    assert repository.get_product("cakes", "P1") == product()
    assert repository.list_categories() == ["cakes"]


def test_malformed_json_is_rejected(tmp_path):
    (tmp_path / "cakes.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(CatalogueValidationError):
        JsonCatalogueRepository(tmp_path).load_category("cakes")


def test_duplicate_ids_are_rejected():
    with pytest.raises(ValidationError, match="duplicate product_id"):
        CategoryCatalogue(category="cakes", products=[product(), product(name="Other")])


def test_invalid_required_fields_are_rejected():
    with pytest.raises(ValidationError):
        product(description="")


def test_visual_interpretation_may_be_null():
    item = product(visual_interpretation=None, visual_interpretation_model="unused")
    assert item.visual_interpretation is None
    assert item.visual_interpretation_model is None


def test_failed_save_preserves_previous_catalogue(tmp_path, monkeypatch):
    repository = JsonCatalogueRepository(tmp_path)
    original = CategoryCatalogue(category="cakes", products=[product()])
    repository.save_category("cakes", original)
    original_text = (tmp_path / "cakes.json").read_text(encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("disk failure")

    monkeypatch.setattr("app.repositories.catalogue_repository.os.replace", fail_replace)
    with pytest.raises(Exception, match="failed to save"):
        repository.save_category(
            "cakes",
            CategoryCatalogue(category="cakes", products=[product(name="Changed")]),
        )
    assert (tmp_path / "cakes.json").read_text(encoding="utf-8") == original_text


def test_category_mismatch_is_rejected(tmp_path):
    payload = CategoryCatalogue(category="flowers", products=[]).model_dump(mode="json")
    (tmp_path / "cakes.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogueValidationError, match="does not match"):
        JsonCatalogueRepository(tmp_path).load_category("cakes")

