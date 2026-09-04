from __future__ import annotations

import json
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import ValidationError

from app.schemas.catalogue import CategoryCatalogue, CatalogueProduct, normalize_category


class CatalogueError(RuntimeError):
    """Base error for canonical catalogue operations."""


class CatalogueNotFoundError(CatalogueError):
    """The requested category has no canonical catalogue file."""


class CatalogueValidationError(CatalogueError):
    """A catalogue failed schema or category validation."""


class CatalogueRepository(ABC):
    @abstractmethod
    def load_category(self, category: str) -> CategoryCatalogue: ...

    @abstractmethod
    def get_product(self, category: str, product_id: str) -> CatalogueProduct | None: ...

    @abstractmethod
    def save_category(self, category: str, catalogue: CategoryCatalogue) -> None: ...

    @abstractmethod
    def list_categories(self) -> list[str]: ...


class JsonCatalogueRepository(CatalogueRepository):
    def __init__(self, catalogue_dir: Path | str) -> None:
        self.catalogue_dir = Path(catalogue_dir)

    def _path(self, category: str) -> Path:
        safe_category = normalize_category(category)
        return self.catalogue_dir / f"{safe_category}.json"

    def load_category(self, category: str) -> CategoryCatalogue:
        path = self._path(category)
        if not path.is_file():
            raise CatalogueNotFoundError(f"catalogue not found for category: {category}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            catalogue = CategoryCatalogue.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise CatalogueValidationError(f"invalid catalogue for category: {category}") from exc
        expected = normalize_category(category)
        if catalogue.category != expected:
            raise CatalogueValidationError(
                f"catalogue category {catalogue.category!r} does not match {expected!r}"
            )
        return catalogue

    def get_product(self, category: str, product_id: str) -> CatalogueProduct | None:
        catalogue = self.load_category(category)
        return next((p for p in catalogue.products if p.product_id == product_id), None)

    def save_category(self, category: str, catalogue: CategoryCatalogue) -> None:
        expected = normalize_category(category)
        validated = CategoryCatalogue.model_validate(catalogue.model_dump())
        if validated.category != expected:
            raise CatalogueValidationError(
                f"catalogue category {validated.category!r} does not match {expected!r}"
            )
        self.catalogue_dir.mkdir(parents=True, exist_ok=True)
        destination = self._path(expected)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.catalogue_dir,
                prefix=f".{expected}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(validated.model_dump(mode="json"), handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, destination)
        except (OSError, ValidationError, ValueError) as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise CatalogueError(f"failed to save catalogue: {expected}") from exc

    def list_categories(self) -> list[str]:
        if not self.catalogue_dir.exists():
            return []
        return [
            self.load_category(path.stem).category
            for path in sorted(self.catalogue_dir.glob("*.json"))
        ]
