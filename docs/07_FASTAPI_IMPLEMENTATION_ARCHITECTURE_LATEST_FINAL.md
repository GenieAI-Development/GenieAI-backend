# GenieAI Recommendation Service
## 07 — FastAPI Implementation Architecture

**Project:** GenieAI  
**Subsystem:** Recommendation Service  
**Status:** **FINAL — Step 7 Implementation Architecture Baseline**  
**Purpose:** Map the finalized GenieAI architecture into concrete Python/FastAPI modules and implementation boundaries.

---

# 1. Implementation Goal

The V1 codebase should prioritize:

- reliable AI workflow behavior;
- testable retrieval/reranking components;
- simple category catalogue management;
- replaceable external integrations;
- minimal infrastructure complexity.

GenieAI V1 deliberately does **not** use PostgreSQL.

Canonical curated product data is stored in validated per-category JSON files.

---

# 2. Final Repository Structure

```text
genieai-backend/
│
├── app/
│   ├── main.py
│   │
│   ├── config/
│   │   └── settings.py
│   │
│   ├── api/
│   │   ├── runtime/
│   │   │   └── recommendations.py
│   │   └── admin/
│   │       ├── products.py
│   │       ├── visual_interpretations.py
│   │       ├── indexes.py
│   │       └── catalogue.py
│   │
│   ├── schemas/
│   │   ├── catalogue.py
│   │   ├── recommendation.py
│   │   ├── gift_box.py
│   │   ├── admin.py
│   │   └── internal.py
│   │
│   ├── repositories/
│   │   └── catalogue_repository.py
│   │
│   ├── integrations/
│   │   ├── kapruka/
│   │   │   ├── client.py
│   │   │   └── normalizer.py
│   │   ├── qdrant/
│   │   │   └── client.py
│   │   └── llm/
│   │       ├── client.py
│   │       └── reliable_executor.py
│   │
│   ├── ingestion/
│   │   ├── product_ingestion.py
│   │   └── visual_interpretation_import.py
│   │
│   ├── indexing/
│   │   ├── embedding_builder.py
│   │   ├── qdrant_indexer.py
│   │   ├── bm25_indexer.py
│   │   └── index_builder.py
│   │
│   ├── core/
│   │   ├── query_understanding/
│   │   │   └── service.py
│   │   ├── planning/
│   │   │   └── recommendation_planner.py
│   │   ├── retrieval/
│   │   │   ├── dense_retriever.py
│   │   │   ├── bm25_retriever.py
│   │   │   └── rrf_fusion.py
│   │   ├── verification/
│   │   │   └── live_product_verifier.py
│   │   └── reranking/
│   │       └── reranker.py
│   │
│   ├── workflows/
│   │   ├── smart_shopping/
│   │   │   └── workflow.py
│   │   └── gift_box/
│   │       ├── context_resolver.py
│   │       └── workflow.py
│   │
│   ├── optimizers/
│   │   └── gift_box_optimizer.py
│   │
│   ├── orchestration/
│   │   └── recommendation_orchestrator.py
│   │
│   ├── sessions/
│   │   ├── store.py
│   │   └── models.py
│   │
│   └── observability/
│       ├── logging.py
│       └── tracing.py
│
├── data/
│   ├── catalogue/
│   │   ├── cakes.json
│   │   ├── flowers.json
│   │   └── ...
│   └── bm25/
│       ├── cakes/
│       ├── flowers/
│       └── ...
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── pyproject.toml
├── .env.example
└── README.md
```

---

# 3. `api/` — HTTP Boundary

`api/` must remain thin.

Responsibilities:

- FastAPI route declarations;
- request validation;
- dependency injection;
- call the correct application/orchestration entry point;
- map internal result to finalized API response.

It must not implement:

- retrieval logic;
- MCP parsing;
- reranking;
- bundle optimization;
- JSON file manipulation.

Runtime endpoint:

```text
POST /api/v1/recommendations
```

Admin endpoints:

```text
POST /api/v1/admin/catalogue/products/import
POST /api/v1/admin/catalogue/visual-interpretations/import
POST /api/v1/admin/catalogue/indexes/build
GET  /api/v1/admin/catalogue/{category}/health
```

---

# 4. `schemas/` — Structured Contracts

Pydantic models live here.

## `catalogue.py`

Defines validated canonical JSON structures:

```text
CatalogueProduct
CategoryCatalogue
```

Key fields:

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

## `recommendation.py`

Runtime API request/response contracts and product-card schemas.

## `gift_box.py`

Gift Box workflow-context and internal Gift Box contracts.

## `admin.py`

Admin ingestion/import/index request schemas.

## `internal.py`

Internal structured outputs used between pipeline components, such as Query Understanding and reranking results.

---

# 5. `repositories/` — Canonical Catalogue Access

V1 contains:

```text
catalogue_repository.py
```

This module owns the catalogue storage abstraction and JSON implementation.

Conceptual contract:

```text
load_category(category)
get_product(category, product_id)
save_category(category, catalogue)
list_categories()
```

The V1 `JsonCatalogueRepository`:

- resolves category file paths;
- validates loaded JSON with Pydantic;
- rejects duplicate product IDs;
- performs atomic writes;
- exposes canonical product objects to the rest of the system.

The rest of GenieAI must not directly call `open("cakes.json")`.

If PostgreSQL is added later, storage can be replaced behind the same repository boundary.

---

# 6. `integrations/` — External Systems

## Kapruka

```text
integrations/kapruka/client.py
integrations/kapruka/normalizer.py
```

`client.py` owns MCP calls.

`normalizer.py` converts Kapruka product responses into canonical catalogue fields, including deterministic weight normalization.

Runtime live verification reuses the same Kapruka product response to extract:

```text
price
in_stock
primary image_url
```

`price` and `in_stock` are authoritative live commerce values.

`image_url` is presentation metadata carried forward with the verified candidate. No additional product lookup is required after final selection solely to obtain the image URL.

## Qdrant

```text
integrations/qdrant/client.py
```

Owns connection/configuration and low-level vector operations.

Core retrieval must call this adapter instead of directly depending on the Qdrant SDK everywhere.

## LLM

```text
integrations/llm/client.py
integrations/llm/reliable_executor.py
```

`reliable_executor.py` implements the Step 6 reliability pattern:

```text
primary model
→ validate
→ bounded retry
→ fallback model(s)
→ validate
→ controlled failure
```

---

# 7. `ingestion/` — Canonical Data Preparation

## `product_ingestion.py`

Flow:

```text
curated product IDs
→ Kapruka client
→ normalizer
→ CatalogueRepository
→ validated category JSON
```

## `visual_interpretation_import.py`

Flow:

```text
external interpretation JSON
→ validate
→ match product_id
→ update optional visual fields
→ CatalogueRepository
```

No embedding generation occurs inside ingestion.

---

# 8. `indexing/` — Derived Search Index Construction

## `embedding_builder.py`

Constructs dense text using:

```text
visual exists
→ description + visual_interpretation

visual absent
→ description only
```

Also calculates SHA-256 `content_hash`.

## `qdrant_indexer.py`

- generates/upserts category vectors;
- stores minimal payload;
- stores `content_hash` in payload;
- removes inactive products;
- supports forced rebuild.

## `bm25_indexer.py`

- uses `bm25s`;
- builds trusted lexical documents;
- excludes visual interpretations;
- rebuilds the full category BM25 index;
- persists the category index using the library-supported save/load mechanism;
- preserves product-ID mapping.

## `index_builder.py`

Coordinates:

```text
validated catalogue
→ Dense/Qdrant update
→ BM25 rebuild
→ coverage verification
```

---

# 9. `core/` — Shared Recommendation Engine

The shared recommendation core must contain no Gift Box-specific business rules.

## Query Understanding

```text
core/query_understanding/service.py
```

Owns:

- category scope;
- stable constraints;
- volatile constraints;
- soft numeric constraints;
- mandatory semantic requirements/exclusions;
- delivery context;
- clarification;
- workflow mismatch detection.

## Recommendation Planning

```text
core/planning/recommendation_planner.py
```

Produces category-specific retrieval plans.

## Retrieval

```text
dense_retriever.py
bm25_retriever.py
rrf_fusion.py
```

Implements category-specific hybrid retrieval.

## Verification

```text
live_product_verifier.py
```

Consumes live price and stock only for candidate verification.

## Reranking

```text
reranker.py
```

Performs semantic eligibility and relevance ranking.

Visual interpretation is included in reranker evidence only when available.

---

# 10. `workflows/` — Workflow-Specific Behavior

## Smart Shopping

```text
workflows/smart_shopping/workflow.py
```

Uses the shared recommendation core and performs final Smart Shopping selection.

## Gift Box

```text
workflows/gift_box/context_resolver.py
workflows/gift_box/workflow.py
```

`context_resolver.py` owns Gift Box-specific values:

```text
recipient
theme
item_count
budget_min_lkr
budget_max_lkr
```

These fields must not leak into shared Query Understanding.

---

# 11. `optimizers/` — Deterministic Bundle Logic

```text
gift_box_optimizer.py
```

Consumes already verified/reranked candidates.

Owns deterministic enforcement of:

- budget;
- exact item count when required;
- required categories;
- exclusions;
- other bundle hard constraints.

LLMs must not override optimizer constraints.

---

# 12. `orchestration/` — Pipeline Sequencing

```text
recommendation_orchestrator.py
```

Owns only stage ordering and branching.

Conceptually:

```text
load/create session
→ Gift Box context resolution when needed
→ Query Understanding
→ clarification/mismatch/delivery short-circuits
→ Recommendation Planning
→ Dense + BM25 retrieval
→ RRF
→ live MCP verification
→ reranking
→ workflow branch
→ final response
→ valid session update
```

The orchestrator must not become a "god class."

It delegates all specialized behavior to the modules above.

---

# 13. `sessions/` — Recommendation Context

```text
store.py
models.py
```

The architecture uses a session abstraction.

Session technology is not required to be finalized before the AI pipeline works.

V1 may begin with a simple in-memory development implementation and later move to Redis without changing workflow contracts.

Session state remains logically separated:

```text
product_search_state
gift_box_state
```

Only validated/resolved state is persisted.

---

# 14. `observability/` — Reliability Diagnostics

```text
logging.py
tracing.py
```

Every runtime request uses the finalized:

```text
session_id
request_id
```

Internal logs should capture:

- pipeline stage timing;
- model retries/fallbacks;
- retrieval candidate counts;
- degraded retrieval mode;
- MCP verification outcomes;
- reranker outcome;
- final result count;
- failure category.

---

# 15. `data/` — V1 Persistent Local Data

## Catalogue

```text
data/catalogue/{category}.json
```

Canonical manually curated category data.

Only `CatalogueRepository` may read/write it directly.

## BM25

```text
data/bm25/{category}/
```

`bm25s`-persisted derived BM25 indexes and their product-ID/document mapping.

This data can be deleted and rebuilt from the canonical catalogue.

Qdrant remains external vector storage.

---

# 16. Explicitly Removed from the V1 Structure

The following previously discussed modules are removed:

```text
db/
models/          # SQLAlchemy database models
migrations/
PostgreSQL repositories
SQLAlchemy
Alembic
psycopg
```

`models/` is not needed as a database-model layer.

Structured domain/API data is represented using Pydantic schemas and ordinary Python dataclasses/types where appropriate.

---

# 17. Avoid Generic Catch-All Modules

Do not introduce broad folders such as:

```text
services/
utils/
helpers/
```

unless a concrete cross-cutting responsibility later justifies them.

Recommendation logic should remain inside its explicit architectural owner.

---

# 18. Dependency Direction

Preferred dependency direction:

```text
API
↓
Orchestrator / Workflow
↓
Shared Core
↓
Repositories + Integrations
↓
JSON / Qdrant / BM25 / Kapruka / LLM providers
```

Lower-level integrations must not import workflow/business logic.

---

# 19. First Implementation Order

With Step 7 finalized, implementation should proceed in this order:

```text
1. config/settings.py
2. schemas/catalogue.py
3. repositories/catalogue_repository.py
4. integrations/kapruka/client.py + normalizer.py
5. ingestion/product_ingestion.py
6. ingestion/visual_interpretation_import.py
7. indexing/embedding_builder.py
8. indexing/qdrant_indexer.py
9. indexing/bm25_indexer.py
10. indexing/index_builder.py
11. validate/index the 642-cake catalogue
12. implement Dense + BM25 + RRF retrieval
13. implement Query Understanding
14. implement live price/stock verification
15. implement reranking
16. complete Smart Shopping end-to-end
17. implement Gift Box workflow + optimizer
18. evaluation/reliability testing
```

Security, production deployment hardening, and advanced caching remain later phases.

---

# 20. Step 7 Final Status

The V1 FastAPI implementation architecture is now finalized around:

- validated per-category JSON canonical catalogues;
- a replaceable catalogue repository boundary;
- category-specific Qdrant + BM25 indexes;
- isolated Kapruka/Qdrant/LLM integrations;
- shared recommendation core;
- separate Smart Shopping and Gift Box workflows;
- deterministic Gift Box optimization;
- centralized orchestration;
- session abstraction;
- request-level observability.

> **Step 7 is complete and frozen as the current V1 implementation architecture baseline.**
