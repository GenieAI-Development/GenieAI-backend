from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import bm25s

from app.schemas.catalogue import CatalogueProduct, CategoryCatalogue


def build_bm25_text(product: CatalogueProduct, category: str) -> str:
    parts = [product.name, product.description, product.vendor, category]
    if product.weight_kg is not None:
        parts.append(f"{product.weight_kg:g} kg")
    return "\n".join(parts)


class BM25Indexer:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def category_dir(self, category: str) -> Path:
        return self.root / category

    def build(self, catalogue: CategoryCatalogue) -> int:
        active = [product for product in catalogue.products if product.is_active]
        corpus = [build_bm25_text(product, catalogue.category) for product in active]
        self.root.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{catalogue.category}.", dir=self.root))
        try:
            if corpus:
                retriever = bm25s.BM25()
                tokens = bm25s.tokenize(corpus, show_progress=False)
                retriever.index(tokens, show_progress=False)
                retriever.save(
                    temp_dir,
                    corpus=[{"product_id": product.product_id} for product in active],
                )
            else:
                (temp_dir / "empty.json").write_text("{}\n", encoding="utf-8")
            destination = self.category_dir(catalogue.category)
            backup = self.root / f".{catalogue.category}.backup"
            if backup.exists():
                shutil.rmtree(backup)
            if destination.exists():
                os.replace(destination, backup)
            try:
                os.replace(temp_dir, destination)
            except Exception:
                if backup.exists():
                    os.replace(backup, destination)
                raise
            if backup.exists():
                shutil.rmtree(backup)
        except Exception:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            raise
        return len(active)

    def load(self, category: str):
        directory = self.category_dir(category)
        if not directory.is_dir():
            raise FileNotFoundError(f"BM25 index not found for category: {category}")
        if (directory / "empty.json").is_file():
            return None
        return bm25s.BM25.load(directory, load_corpus=True)

    def indexed_ids(self, category: str) -> set[str]:
        retriever = self.load(category)
        if retriever is None:
            return set()
        corpus = retriever.corpus or []
        return {str(item["product_id"]) for item in corpus}

    def search(self, category: str, query: str, limit: int) -> list[tuple[str, float]]:
        retriever = self.load(category)
        if retriever is None:
            return []
        corpus = retriever.corpus or []
        if not corpus:
            return []
        query_tokens = bm25s.tokenize(query, show_progress=False)
        results, scores = retriever.retrieve(
            query_tokens,
            k=min(limit, len(corpus)),
            show_progress=False,
        )
        return [
            (str(item["product_id"]), float(score))
            for item, score in zip(results[0], scores[0], strict=True)
        ]
