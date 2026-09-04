# GenieAI Recommendation Service
## 08 — Implementation Contracts

**Project:** GenieAI  
**Subsystem:** Recommendation Service  
**Status:** **FINAL — Step 8 Implementation Contracts Baseline**  
**Purpose:** Freeze the small set of concrete storage, retrieval, configuration, and dependency contracts required before implementation begins.

---

# 1. Canonical Category JSON Contract

GenieAI V1 stores one validated canonical JSON catalogue per product category.

Example:

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

## 1.1 Top-Level Fields

Required:

```text
category
products
```

`category` is the canonical category slug represented by the file.

`products` is the curated product list for that category.

## 1.2 Required Product Fields

```text
product_id
name
description
vendor
is_active
```

## 1.3 Optional Product Fields

```text
weight_kg
price_snapshot_lkr
visual_interpretation
visual_interpretation_model
```

`visual_interpretation` is optional enrichment.

For a product without visual enrichment:

```json
{
  "visual_interpretation": null,
  "visual_interpretation_model": null
}
```

## 1.4 Fields Not Stored in Canonical JSON

Do not store operational/index-state metadata such as:

```text
created_at
updated_at
embedding_status
bm25_status
source_updated_at
```

Do not store:

```text
image_url
current stock
authoritative current price
```

`price_snapshot_lkr` may exist only as a non-authoritative ingestion snapshot.

---

# 2. Runtime Image URL Contract

`image_url` is not persisted in the canonical JSON catalogue.

The existing live product verification call is reused:

```text
kapruka_get_product(product_id)
        ↓
extract
- price
- in_stock
- primary image URL
```

Recommended primary image selection:

```text
images[0] → image_url
```

Semantics:

```text
price       → authoritative live commerce value
in_stock    → authoritative live commerce value
image_url   → presentation metadata
```

The image URL is carried forward with the verified candidate and reused when creating the final frontend product card.

No additional product lookup is required after final selection solely to obtain the image URL.

`image_url` must not be included in:

- canonical JSON
- dense embedding text
- Qdrant payload
- BM25 documents

---

# 3. Qdrant Contract

## 3.1 Collection Topology

Use one Qdrant collection per category.

Examples:

```text
kapruka_cakes
kapruka_flowers
kapruka_chocolates
```

Naming contract:

```text
{QDRANT_COLLECTION_PREFIX}{category}
```

Default prefix:

```text
kapruka_
```

## 3.2 Embedding Configuration

```text
model     = text-embedding-3-small
dimension = 1536
distance  = Cosine
```

## 3.3 Dense Text

```text
visual interpretation exists
→ description + visual_interpretation

visual interpretation absent
→ description only
```

## 3.4 Qdrant Payload

Exact minimal V1 payload:

```text
product_id
vendor
weight_kg
content_hash
```

`content_hash` is the SHA-256 hash of the exact dense embedding text used to create the vector.

It is used to detect whether a stored vector must be regenerated.

Do not store in Qdrant payload:

```text
description
visual_interpretation
price
stock
image_url
```

Qdrant is a derived dense retrieval index, not the canonical product store.

---

# 4. BM25 Persistence Contract

BM25 remains separate from Qdrant.

Each category has its own lexical index:

```text
data/
└── bm25/
    ├── cakes/
    ├── flowers/
    └── ...
```

V1 uses `bm25s` for indexing/search and its supported save/load persistence mechanism.

Each persisted category index must preserve the mapping from BM25 document positions/results back to canonical Kapruka `product_id` values.

The index is derived data and must always be rebuildable from the canonical category JSON.

## 4.1 BM25 Source Text

Use trusted lexical product fields only:

```text
product name
original description
vendor
category
reliable structured textual attributes where useful
```

Never include:

```text
visual_interpretation
generated semantic analysis
image_url
live price
live stock
```

## 4.2 Rebuild Strategy

V1 uses a full BM25 rebuild per affected category.

---

# 5. Application Runtime Baseline

```text
Python 3.12
FastAPI
Pydantic v2
pydantic-settings
```

---

# 6. Core Dependency Baseline

Main libraries:

```text
fastapi[standard]   → API/runtime
pydantic            → schemas and validation
pydantic-settings   → environment/configuration

openai              → embeddings and OpenAI LLM calls
qdrant-client       → dense vector storage/search
bm25s               → lexical BM25 indexing/search/persistence
mcp                  → Kapruka MCP client integration
tenacity             → bounded retries
httpx                → HTTP integrations when needed

pytest
pytest-asyncio       → testing
```

Exact package versions should be pinned once a tested working environment is established.

---

# 7. Configuration Contract

Core environment/settings values:

```text
OPENAI_API_KEY

QDRANT_URL
QDRANT_API_KEY

CATALOGUE_DIR=data/catalogue
BM25_DIR=data/bm25

EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536

QDRANT_COLLECTION_PREFIX=kapruka_

DENSE_TOP_K=40
BM25_TOP_K=40
FUSED_TOP_K=20
```

The following remain configurable and do not need exact values frozen before implementation:

```text
LLM model names
fallback model order
retry counts
MCP concurrency
timeouts
relevance thresholds
cache TTLs
```

---

# 8. Final Retrieval Boundary

At runtime:

```text
User query
    ├──→ Dense retrieval → Qdrant
    └──→ BM25 retrieval  → persisted bm25s category index
                              ↓
                             RRF
                              ↓
                     candidate verification
                              ↓
                 kapruka_get_product()
                    ├── live price
                    ├── live stock
                    └── image_url
```

Only live price and stock are used as authoritative volatile commerce values.

The image URL is reused as presentation metadata.

---

# 9. Step 8 Final Status

The following implementation contracts are now frozen for GenieAI V1:

1. validated per-category canonical JSON schema;
2. required and optional canonical product fields;
3. no stored image URL in canonical JSON;
4. image URL reused from the existing live MCP verification response;
5. category-specific Qdrant collections;
6. OpenAI `text-embedding-3-small`, 1536 dimensions, Cosine distance;
7. minimal Qdrant payload: `product_id`, `vendor`, `weight_kg`, `content_hash`;
8. separate category-specific BM25 indexes using `bm25s`;
9. Python 3.12 / FastAPI / Pydantic v2 runtime baseline;
10. core dependency and environment-variable baseline.

> **Step 8 is complete. Architecture design should now stop unless implementation exposes a concrete issue. The next phase is actual implementation.**
