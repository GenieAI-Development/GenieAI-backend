# AGENTS.md — GenieAI Recommendation Service

## Project Mission

GenieAI is an AI-powered Kapruka product recommendation backend.

This repository implements the Python FastAPI Recommendation Service.

Supported workflows:

```text
product_recommendation
gift_box
```

The primary engineering priority is:

> Reliable recommendation quality and AI workflow correctness before infrastructure/security complexity.

---

## Architecture Authority

The architecture `.md` files supplied with the project are authoritative.

Do not silently redesign finalized architectural decisions.

When implementation choices conflict with architecture:

1. prefer explicit finalized decisions;
2. prefer newer/more-specific implementation contracts;
3. Step 8 implementation contracts govern concrete V1 implementation details.

Do not reintroduce deprecated architecture.

---

## No PostgreSQL in V1

Do not add:

```text
PostgreSQL
SQLAlchemy
Alembic
psycopg
database migrations
```

Canonical product data is stored as validated per-category JSON.

```text
data/catalogue/{category}.json
```

All catalogue access must go through `CatalogueRepository` / `JsonCatalogueRepository`.

Do not directly manipulate catalogue JSON from arbitrary modules.

---

## Canonical Product Contract

Required:

```text
product_id
name
description
vendor
is_active
```

Optional:

```text
weight_kg
price_snapshot_lkr
visual_interpretation
visual_interpretation_model
```

Do not store:

```text
image_url
current stock
authoritative live price
embedding status
BM25 status
database-style timestamps
```

Use Pydantic validation and atomic file writes.

---

## Visual Interpretation

Visual interpretation is OPTIONAL.

Dense text:

```text
visual exists:
description + visual_interpretation

visual absent:
description only
```

BM25 must never contain visual interpretation text.

A missing visual interpretation must not make a product recommendation-unready.

---

## Qdrant

One collection per category:

```text
kapruka_{category}
```

Embedding:

```text
text-embedding-3-small
1536 dimensions
Cosine
```

Exact payload:

```text
product_id
vendor
weight_kg
content_hash
```

Do not store description, visual interpretation, price, stock, or image URL in Qdrant payload.

`content_hash` is SHA-256 of exact Dense embedding text.

---

## BM25

BM25 is separate from Qdrant.

Use `bm25s`.

Persist indexes under:

```text
data/bm25/{category}/
```

Use full category rebuilds in V1.

BM25 uses trusted lexical product data only.

---

## Kapruka MCP

Kapruka MCP is the live commerce authority.

During candidate verification, call:

```text
kapruka_get_product(product_id)
```

From the SAME response extract:

```text
price
in_stock
primary image_url
```

Rules:

```text
price       = authoritative current price
in_stock    = authoritative current availability
image_url   = presentation metadata
```

Do not perform a second product lookup solely for image URL after final selection.

Never treat stored price snapshots or stock as authoritative.

---

## Hybrid Retrieval

Normal:

```text
Dense + BM25 → RRF
```

Configuration baseline:

```text
Dense Top 40
BM25 Top 40
RRF Top 20
```

Use the original full user query.

Stable deterministic constraints may pre-filter.

Current price and stock must be enforced only using live MCP verification.

If one retriever fails, safe degraded single-retriever mode is allowed.

If both fail, return controlled temporary failure.

---

## Query Understanding

Shared Query Understanding owns:

```text
original query
category scope
stable constraints
volatile constraints
soft numeric constraints
mandatory semantic requirements
mandatory semantic exclusions
delivery context
clarification
workflow mismatch
```

Do not build a separate semantic-preference extraction branch before retrieval.

Preserve the original full user query.

---

## Gift Box Separation

Gift Box-specific fields belong to the Gift Box Context Resolver:

```text
recipient
theme
item_count
budget_min_lkr
budget_max_lkr
```

They must not leak into shared Query Understanding.

Gift Box final bundle construction is deterministic Python.

LLMs must not enforce hard bundle constraints.

---

## LLM Reliability

Every LLM decision stage uses:

```text
primary
→ validate
→ bounded retry
→ fallback
→ validate
→ controlled failure
```

Never allow malformed model output downstream.

Never silently skip reranking.

---

## Runtime Result Rules

Smart Shopping:

```text
up to 12 final products
```

Do not force irrelevant products to reach 12.

Every frontend product card contains:

```text
product_id
name
price_lkr
image_url
vendor
reason
```

`price_lkr` is live.

`image_url` comes from the live MCP verification response.

`reason` must be short and evidence-grounded.

---

## API Semantics

Primary runtime route:

```text
POST /api/v1/recommendations
```

Admin routes:

```text
POST /api/v1/admin/catalogue/products/import
POST /api/v1/admin/catalogue/visual-interpretations/import
POST /api/v1/admin/catalogue/indexes/build
GET /api/v1/admin/catalogue/{category}/health
```

Workflow values:

```text
product_recommendation
gift_box
```

Outcome field:

```text
response_type
```

Allowed runtime response types:

```text
recommendation
limited_results
clarification
workflow_mismatch
delivery_unavailable
temporary_unavailable
```

Do not change `response_type` back to `type`.

---

## Sessions

```text
session_id = conversation
request_id = single request/turn
```

Frontend does not create session IDs.

Failed requests must not corrupt previously valid session state.

Do not persist live price/stock as durable session truth.

---

## Reliability

Distinguish:

```text
real catalogue scarcity → limited_results
system failure          → temporary_unavailable
```

Individual MCP product failure:

```text
drop candidate
continue
```

Broad MCP verification failure:

```text
fail closed
```

Never fabricate recommendations that violate hard constraints.

---

## Repository Structure

Keep responsibilities explicit.

Use:

```text
api/
schemas/
repositories/
integrations/
ingestion/
indexing/
core/
workflows/
optimizers/
orchestration/
sessions/
observability/
```

Avoid generic dumping grounds:

```text
services/
utils/
helpers/
```

unless a clearly justified cross-cutting responsibility appears.

`api/` must remain thin.

`orchestration/` coordinates stages but does not implement their business logic.

---

## Technology Baseline

```text
Python 3.12
FastAPI
Pydantic v2
pydantic-settings
openai
qdrant-client
bm25s
mcp
tenacity
httpx
pytest
pytest-asyncio
```

Never hardcode secrets.

Use `.env` / settings.

---

## Testing Expectations

Every significant module should have tests.

Prioritize tests for:

```text
catalogue validation
atomic JSON writes
MCP normalization
weight normalization
Dense text/hash construction
Qdrant indexing
BM25 persistence/search
RRF
live verification
LLM retries/fallback
reranking
Gift Box hard constraints
API validation
session behavior
failure semantics
```

Do not mark work complete with failing core tests.

---

## Implementation Style

Prefer:

```text
small focused modules
type hints
async external I/O
dependency injection
structured contracts
explicit failures
testability
```

Avoid:

```text
god classes
circular dependencies
hidden side effects
silent exception swallowing
duplicated integration calls
unnecessary abstractions
premature infrastructure
```

---

## Security Priority

Security/authentication is not the current primary implementation objective.

Still:

* never commit secrets;
* validate input;
* handle paths safely;
* do not load arbitrary untrusted serialized data.

Do not let security infrastructure distract from completing the reliable V1 recommendation workflow.

---

## Completion Standard

Before considering a task finished:

```text
run tests
fix import/runtime failures
remove accidental placeholders
verify architecture compliance
verify no deprecated PostgreSQL code exists
verify FastAPI still starts
```

When modifying architecture-sensitive code, re-check the relevant architecture `.md` files before making changes.
