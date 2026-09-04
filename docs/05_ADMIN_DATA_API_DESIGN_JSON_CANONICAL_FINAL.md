# GenieAI — Step 5: Admin / Data API Design

## 1. Purpose

The Admin / Data API supports the operations required to prepare GenieAI's curated recommendation catalogue and search indexes.

The current priority is reliable AI/data workflow behavior, not authentication or authorization design.

GenieAI V1 uses validated **per-category JSON catalogues**, not PostgreSQL.

Admin routes remain inside the same FastAPI Recommendation Service under a separate router/module.

```text
app/
├── api/
│   ├── runtime/
│   │   └── recommendations.py
│   └── admin/
│       ├── products.py
│       ├── visual_interpretations.py
│       ├── indexes.py
│       └── catalogue.py
```

Runtime endpoint:

```text
POST /api/v1/recommendations
```

---

## 2. Admin Endpoint 1 — Product Ingestion

### Endpoint

```http
POST /api/v1/admin/catalogue/products/import
```

### Purpose

Import manually curated Kapruka product IDs into the canonical JSON catalogue for a category.

### Example Request

```json
{
  "category": "cakes",
  "product_ids": [
    "cake00KA001685",
    "cake00KA001686"
  ]
}
```

### Backend Flow

```text
validate requested category
→ normalize/deduplicate IDs
→ fetch each exact product through kapruka_get_product()
→ validate MCP response
→ normalize canonical fields
→ merge/upsert records by product_id
→ validate final category catalogue
→ atomically replace category JSON file
→ skip/report failed product IDs
```

Failed/unknown products must not create empty or incomplete records.

V1 needs only a simple success/failure result and failed product IDs where applicable.

### MCP → Canonical Product Mapping

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

`price_snapshot_lkr` is non-authoritative.

### Weight Normalization

1. Prefer an explicitly labeled KG value in the description.
2. Otherwise convert an explicitly labeled pounds value to kg.
3. If the unit cannot be determined reliably:

```text
weight_kg = null
```

4. Never guess an unlabeled unit.

---

## 3. Admin Endpoint 2 — Visual Interpretation Import

### Endpoint

```http
POST /api/v1/admin/catalogue/visual-interpretations/import
```

### Purpose

Import externally generated visual interpretations for categories/products that use visual enrichment.

Visual interpretation is optional across GenieAI.

Categories without visual interpretations do not need to call this endpoint.

### Example Request

```json
{
  "category": "cakes",
  "model_name": "Qwen3.8-Max",
  "replace_existing": false,
  "items": [
    {
      "product_id": "cake00KA001685",
      "visual_interpretation": "Pastel floral birthday cake..."
    }
  ]
}
```

### Backend Flow

```text
validate category
→ load validated category JSON
→ validate interpretation records
→ match product_id against existing category products
→ reject unknown/category-mismatched IDs
→ update visual_interpretation fields
→ validate final category catalogue
→ atomically replace category JSON file
```

### Rules

- `product_id` must already exist in the requested category catalogue.
- `visual_interpretation` must be non-empty.
- `model_name` is optional provenance metadata.
- `replace_existing=false` remains the safe default.
- BM25 is unaffected.
- No explicit "stale embedding" database flag is required.

When an interpretation changes, the next index build recomputes dense text and detects the changed SHA-256 hash against the hash stored in Qdrant payload.

---

## 4. Admin Endpoint 3 — Build / Rebuild Search Indexes

### Endpoint

```http
POST /api/v1/admin/catalogue/indexes/build
```

### Example Request

```json
{
  "category": "cakes",
  "rebuild": false
}
```

### Purpose

Build or rebuild the category-specific Qdrant and BM25 indexes from the validated canonical JSON catalogue.

### Normal Build — `rebuild=false`

```text
validate category JSON
→ select active products
→ construct dense embedding text
→ compute SHA-256 content hashes
→ compare hashes with existing Qdrant payloads
→ generate/upsert only missing or changed dense vectors
→ rebuild the complete category BM25 index
→ verify indexed product coverage
```

Dense rule:

```text
visual interpretation exists
→ description + visual interpretation

visual interpretation absent
→ description only
```

Dense baseline:

```text
OpenAI text-embedding-3-small
dimension = 1536
```

Qdrant remains category-specific.

BM25 remains category-specific and excludes visual interpretations.

### Forced Rebuild — `rebuild=true`

```text
regenerate all dense embeddings for active products
→ rebuild/recreate category Qdrant contents
→ rebuild complete category BM25 index
→ verify coverage
```

### Initial Production Readiness

For a category to be ready:

```text
100% of active curated products intended for recommendation
must exist in Dense/Qdrant and BM25.
```

Visual interpretation coverage is informational only.

---

## 5. Admin Endpoint 4 — Catalogue Health / Coverage

### Endpoint

```http
GET /api/v1/admin/catalogue/{category}/health
```

### Purpose

Report whether the category JSON and both retrieval indexes are ready for recommendation.

### Example Response

```json
{
  "category": "cakes",
  "ready": true,
  "active_products": 642,
  "visual_interpretations_available": 642,
  "dense_not_indexed": 0,
  "bm25_not_indexed": 0
}
```

A category without visual enrichment may still be fully ready:

```json
{
  "category": "flowers",
  "ready": true,
  "active_products": 500,
  "visual_interpretations_available": 0,
  "dense_not_indexed": 0,
  "bm25_not_indexed": 0
}
```

### Readiness Flow

```text
load + validate category JSON
→ determine active product IDs
→ compare against Qdrant indexed product IDs
→ compare against BM25 indexed product IDs
→ report visual interpretation count as informational enrichment coverage
```

`ready=true` only depends on required active products being validly present in both retrieval indexes.

---

## 6. JSON Safety Rules

Because JSON is the canonical V1 store:

- all catalogue reads pass schema validation;
- duplicate `product_id` values are rejected;
- writes use temporary-file + atomic replace;
- runtime recommendation code never directly modifies catalogue files;
- only ingestion/import pipelines write canonical catalogue data;
- a failed import must leave the previous valid catalogue intact.

These safeguards replace database transaction guarantees for V1.

---

## 7. Catalogue Repository Boundary

Admin code should access category files through:

```text
CatalogueRepository
```

V1 implementation:

```text
JsonCatalogueRepository
```

Responsibilities include:

```text
load_category(category)
get_product(category, product_id)
save_category(category, catalogue)
list_categories()
```

The repository validates and atomically writes catalogue data.

This keeps future migration to PostgreSQL possible without changing the recommendation workflow.

---

## 8. Deliberately Excluded from V1

### Dedicated Product Re-sync Endpoint

Not required.

If a stable product must be refreshed, submit that product ID through the existing product-ingestion endpoint.

### Detailed Batch Accounting

Not required.

Correct ingestion matters more than elaborate admin reporting.

### Authentication / Authorization

Deferred.

The immediate priority remains AI workflow reliability.

### Database Infrastructure

Not used in V1:

```text
PostgreSQL
SQLAlchemy
Alembic
database migrations
database transaction layer
```

---

## 9. Final V1 Admin / Data API Surface

```text
POST /api/v1/admin/catalogue/products/import
POST /api/v1/admin/catalogue/visual-interpretations/import
POST /api/v1/admin/catalogue/indexes/build
GET  /api/v1/admin/catalogue/{category}/health
```

These four endpoints are sufficient to:

1. ingest the manually curated product catalogue;
2. optionally import visual interpretations;
3. build Dense/Qdrant + BM25 indexes;
4. verify recommendation readiness.

> **Step 5 is complete and frozen as the V1 JSON-based Admin / Data API baseline.**
