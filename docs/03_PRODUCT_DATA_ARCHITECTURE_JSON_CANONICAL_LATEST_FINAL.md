# GenieAI Recommendation Service
## 03 — Product Data Architecture and Storage Design

**Project:** GenieAI  
**Subsystem:** Recommendation Service  
**Status:** **FINAL — Step 3 Architecture Baseline**  
**Purpose:** Define the canonical product data model, source-of-truth hierarchy, storage ownership, indexing inputs, and category-level data lifecycle.

---

# 1. Source-of-Truth Hierarchy

GenieAI V1 uses a deliberately simple storage architecture:

```text
Kapruka MCP
    ↓
Upstream product source + live commerce source of truth
    ↓
Validated per-category JSON catalogue
    ↓
Canonical recommendation-data store
    ↓
Derived search indexes
    ├── Qdrant
    └── BM25
```

Responsibilities:

- **Kapruka MCP** → upstream product source and authoritative live price/stock source
- **Per-category JSON catalogue** → canonical stable recommendation data
- **Qdrant** → derived dense vector retrieval index
- **BM25** → derived lexical retrieval index

Qdrant and BM25 must remain rebuildable from the validated category JSON catalogue.

PostgreSQL, SQLAlchemy, Alembic, and database migrations are intentionally excluded from GenieAI V1.

---

# 2. Canonical Product Identifier

Kapruka `product_id` is the canonical identifier throughout the Recommendation Service.

The same `product_id` is used across:

- category JSON files
- Qdrant payloads
- BM25 documents
- session state
- live MCP verification
- reranking
- Gift Box optimization
- product-card assembly
- API responses

---

# 3. Canonical Product Store

The canonical curated catalogue is stored as one validated JSON file per recommendation category.

Example:

```text
data/
└── catalogue/
    ├── cakes.json
    ├── flowers.json
    ├── chocolates.json
    └── perfumes.json
```

The category file defines the curated recommendation universe for that category.

For cakes, the current curated universe remains the selected 642 products.

The catalogue files may live inside the repository for V1 or be mounted/provided as deployment data later. They must only be modified through controlled ingestion/import code.

---

# 4. Category JSON Structure

Each file contains one category and its canonical product records.

Conceptually:

```json
{
  "category": "cakes",
  "products": [
    {
      "product_id": "cake00KA001685",
      "name": "Springtime Birthday Ribbon Cake",
      "description": "...",
      "vendor": "Kapruka Cakes",
      "weight_kg": 1.25,
      "price_snapshot_lkr": 5770,
      "is_active": true,
      "visual_interpretation": "Pastel floral birthday cake...",
      "visual_interpretation_model": "Qwen3.8-Max"
    }
  ]
}
```

For categories/products without visual interpretations:

```json
{
  "visual_interpretation": null,
  "visual_interpretation_model": null
}
```

Category identity is normally implied by the file, but the top-level `category` value is retained for validation.

---

# 5. Stable Product Data

Stable product fields are ingested from Kapruka MCP and normalized into the category JSON catalogue.

Canonical fields for V1:

```text
product_id
name
description
vendor
weight_kg
price_snapshot_lkr
is_active
visual_interpretation
visual_interpretation_model
```

`price_snapshot_lkr` is optional and non-authoritative.

`visual_interpretation` and `visual_interpretation_model` are optional enrichment fields.

---

# 6. Visual Interpretations

Visual interpretations are optional semantic/visual enrichment.

They must remain a separate field from the original product description.

```text
description
visual_interpretation
```

A product/category must not be considered unready merely because no visual interpretation exists.

For categories such as cakes where externally generated interpretations are available, GenieAI may maintain full enrichment coverage as a quality target.

For categories without interpretations, dense retrieval uses canonical textual product data only.

---

# 7. Dense Embedding Input

The embedding input must be reproducibly constructed.

Current rule:

```text
If visual_interpretation exists:
    dense_text = description + visual_interpretation

If visual_interpretation does not exist:
    dense_text = description
```

Visual interpretation is therefore optional enrichment, not an indexing prerequisite.

A fixed versioned template should be used for dense text construction.

Baseline embedding configuration:

```text
OpenAI text-embedding-3-small
dimension = 1536
distance = Cosine
```

---

# 8. BM25 Indexing Policy

BM25 must never include visual-interpretation text or generated semantic interpretation text.

BM25 source text uses trusted lexical product fields only.

Recommended fields:

```text
product name
original Kapruka description
vendor
category
reliable structured textual attributes such as weight
```

Therefore:

```text
Dense retrieval text
=
description
+ optional visual interpretation
```

```text
BM25 retrieval text
=
trusted lexical product text only
```

Visual interpretations remain excluded because lexical matching can incorrectly reward negated or inferred terms.

---

# 9. Category-Specific Retrieval Indexes

Each category has separate retrieval boundaries.

```text
cakes
├── Qdrant collection: kapruka_cakes
└── BM25 index: cakes_bm25

flowers
├── Qdrant collection: kapruka_flowers
└── BM25 index: flowers_bm25
```

Category identity is implied by the selected retrieval index.

---

# 10. Qdrant Payload

Qdrant stores the vector plus minimal stable/retrieval-maintenance metadata.

Exact V1 payload:

```text
product_id
vendor
weight_kg
content_hash
```

`content_hash` is the SHA-256 hash of the exact dense embedding text and is used to detect whether the vector is still current.

Do not use Qdrant as the canonical product store.

---

# 11. Dense Change Detection

For every active product:

```text
construct current dense_text
→ calculate SHA-256 content_hash
→ compare with Qdrant payload content_hash
```

If hashes match:

```text
skip embedding regeneration
```

If the product is missing from Qdrant or the hash changed:

```text
generate embedding
→ upsert vector + current payload
```

This allows incremental dense indexing without PostgreSQL metadata tables.

---

# 12. BM25 Persistence and Rebuild Strategy

Each category has its own persisted BM25 index managed using `bm25s`.

The persisted index must preserve the canonical `product_id` mapping for every document/result.

V1 uses full per-category BM25 rebuilds.

```text
validated category JSON
→ construct all active BM25 documents
→ rebuild category BM25 index
→ persist index + product ID mapping
```

Because catalogue sizes are modest, this is intentionally simpler than incremental BM25 mutation.

---

# 13. Price and Stock

Current price and stock are volatile.

They are not authoritative in the category JSON catalogue.

`price_snapshot_lkr` may exist only as a convenience/diagnostic snapshot.

At recommendation time:

```text
retrieved candidate
→ kapruka_get_product()
→ current price
→ current in_stock
```

Only live MCP values are authoritative for volatile constraint validation.

---

# 14. Product Images and Presentation Data

Product image binaries and image URLs are not canonical catalogue data.

They must not be included in:

- dense embedding text
- BM25 text

The primary image URL is not stored canonically. It is extracted from the same `kapruka_get_product()` response already used for live price/stock verification and carried forward with the verified candidate for final product-card assembly. No additional MCP lookup is required solely for the image URL.

---

# 15. Product Ingestion Pipeline

## 15.1 Purpose

Convert a manually curated set of Kapruka product IDs into normalized category JSON records.

## 15.2 Input

```text
category
+
curated product IDs
```

For cakes, this is the selected 642-product set.

## 15.3 Flow

```text
validate category
→ normalize/deduplicate IDs
→ fetch each product using kapruka_get_product()
→ validate MCP response
→ normalize canonical fields
→ merge/upsert by product_id
→ validate complete category object
→ atomically replace category JSON file
```

A failed or unknown product must not create an empty/incomplete record.

Re-ingesting an existing product ID updates the canonical product record safely.

---

# 16. MCP → Canonical Product Normalization

V1 mapping:

```text
MCP field                    → canonical JSON field

id                           → product_id
name                         → name
description                  → description
category.slug                → validate requested category
attributes.vendor            → vendor
price.amount                 → price_snapshot_lkr
```

Do not persist as canonical product fields:

```text
in_stock
stock_level
images
variants
shipping
rating
url
summary
compare_at_price
```

---

# 17. Weight Normalization

Weight normalization must be deterministic.

Rule:

1. Prefer an explicitly labeled KG value in the product description.
2. Otherwise, convert an explicitly labeled pounds value to kilograms.
3. If the unit cannot be determined reliably, use:

```text
weight_kg = null
```

4. Never guess an unlabeled unit.

Example:

```text
2.77 Lbs (1.25 KG)
→ weight_kg = 1.25
```

---

# 18. Visual Interpretation Import Pipeline

Visual interpretation import is optional and used only for categories/products with external visual enrichment.

Flow:

```text
category
+ interpretation records
→ validate structure
→ match product_id against category catalogue
→ reject unknown/category-mismatched IDs
→ update visual_interpretation fields
→ validate category JSON
→ atomically replace category JSON file
```

Replacing an interpretation does not require a database status update.

Instead, the next index build reconstructs `dense_text`, computes its `content_hash`, notices the Qdrant hash mismatch, and regenerates that vector.

BM25 is unaffected.

---

# 19. JSON Validation and Atomic Writes

Every category catalogue must be validated before it becomes canonical data.

Recommended implementation:

- Pydantic catalogue/product schemas
- reject malformed records
- reject duplicate `product_id` values
- reject category mismatch
- reject invalid numeric fields
- use temporary-file + atomic rename/replace when saving

Runtime recommendation code must never directly modify catalogue JSON.

All writes go through the catalogue repository / ingestion pipelines.

---

# 20. Catalogue Repository Boundary

The rest of the recommendation system must not depend directly on JSON file operations.

Use a repository abstraction:

```text
CatalogueRepository
```

V1 implementation:

```text
JsonCatalogueRepository
```

Core operations:

```text
load_category(category)
get_product(category, product_id)
save_category(category, catalogue)
list_categories()
```

This keeps storage replaceable.

If PostgreSQL is introduced later, a `PostgresCatalogueRepository` can implement the same contract without redesigning retrieval/reranking/workflow logic.

---

# 21. Recommendation Readiness

Readiness is derived from the active catalogue and retrieval indexes.

A product is recommendation-ready when:

```text
is_active = true
AND
a valid dense vector exists in the correct Qdrant collection
AND
a BM25 document exists in the correct category BM25 index
```

Visual interpretation is optional and is not part of the universal readiness condition.

A category is ready when all active curated products intended for recommendation satisfy these indexing requirements.

---

# 22. Rebuildability Principle

Both indexes are derived from canonical JSON.

```text
validated category JSON
        ↓
dense builder → Qdrant

validated category JSON
        ↓
BM25 builder → BM25 index
```

Deleting/recreating the indexes must not destroy canonical recommendation data.

---

# 23. Deliberately Excluded from V1

The following are intentionally excluded:

```text
PostgreSQL
SQLAlchemy
Alembic
database migrations
database transaction layer
database-specific repositories
embedding metadata tables
BM25 metadata tables
```

The current priority is recommendation quality and AI workflow reliability.

---

# 24. Final Step 3 Decisions

1. Kapruka `product_id` is canonical everywhere.
2. Kapruka MCP remains the upstream product source and live price/stock source.
3. One validated JSON file per category is the V1 canonical recommendation store.
4. Catalogue JSON defines the manually curated recommendation universe.
5. Visual interpretation is optional enrichment.
6. Dense text uses description + visual interpretation when available, otherwise description only.
7. BM25 never includes visual interpretations.
8. Qdrant collections remain separate by category.
9. BM25 indexes remain separate by category.
10. Dense content hashes are stored in Qdrant payload for incremental reindex detection.
11. BM25 uses full category rebuilds in V1.
12. All catalogue writes are validated and atomic.
13. Runtime code accesses catalogue data through `CatalogueRepository`.
14. Price/stock snapshots are non-authoritative; final price/stock come from live MCP.
15. Product image URLs are not canonical recommendation data.
16. Recommendation readiness requires active product + Dense/Qdrant + BM25, not visual interpretation.
17. PostgreSQL is deferred and may be introduced later behind the repository abstraction.

> **Step 3 is complete and frozen as the V1 JSON-based Product Data Architecture baseline.**
