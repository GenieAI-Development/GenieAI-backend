# GenieAI Recommendation Service

GenieAI is a Python 3.12 FastAPI service that powers Kapruka Smart Shopping
(`product_recommendation`) and Gift Box Builder (`gift_box`) recommendations. It
maintains curated stable product data, performs hybrid retrieval, verifies live
commerce fields, reranks candidates, and returns presentation-ready product cards.

## Architecture

The service uses one reusable recommendation pipeline with workflow-specific final
selection:

```text
validated request + session
  -> Gift Box context resolution (gift_box only)
  -> shared query understanding
  -> category planning
  -> Dense/Qdrant + BM25 retrieval
  -> reciprocal-rank fusion
  -> live Kapruka verification
  -> semantic eligibility/reranking
  -> Smart Shopping selection or deterministic Gift Box optimization
  -> response generation
```

Canonical data is validated JSON at `data/catalogue/{category}.json`. Qdrant and
the category-specific `bm25s` files under `data/bm25/{category}/` are rebuildable
derived indexes. Kapruka MCP is authoritative for current price and stock and also
supplies the product-card image in that same verification response.

Key source areas:

```text
app/api/             thin runtime and admin HTTP routes
app/schemas/         API, catalogue, Gift Box, and internal contracts
app/repositories/    canonical catalogue boundary and atomic JSON storage
app/integrations/    Kapruka MCP, Qdrant, and structured OpenAI adapters
app/ingestion/       product and visual-interpretation imports
app/indexing/        Dense/Qdrant and BM25 construction/health
app/core/            understanding, planning, retrieval, verification, reranking
app/workflows/       Smart Shopping and Gift Box final behavior
app/optimizers/      deterministic Gift Box constraint optimizer
app/orchestration/   stage sequencing and failure propagation
app/sessions/        replaceable session abstraction and in-memory V1 store
app/observability/   structured events and request/stage timing
tests/               unit, integration, and end-to-end tests
```

The frozen design decisions are in `docs/01_...md` through `docs/08_...md`.

## Prerequisites

- Python 3.12
- A running Qdrant service
- An OpenAI API key for embeddings and structured LLM stages
- Access to the Kapruka Streamable HTTP MCP endpoint

The repository expects the existing `.venv` environment. On Windows:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

Copy `.env.example` to `.env` and configure at least:

```dotenv
OPENAI_API_KEY=...
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
KAPRUKA_MCP_URL=https://mcp.kapruka.com/mcp
```

Model names, retry count, retrieval depths, MCP concurrency, and storage paths are
also configurable in `.env.example`. Secrets must remain in `.env` or the deployment
secret store.

For local Qdrant, one option is:

```powershell
docker run --name genieai-qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health and interactive API docs are available at `/healthz` and `/docs`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Tests inject fakes for credentials-dependent integrations. Production adapters are
not replaced by mocks in application code.

## Prepare a Catalogue

Import curated product IDs. Invalid or unavailable IDs are reported and never create
partial records:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/admin/catalogue/products/import `
  -H "Content-Type: application/json" `
  -d '{"category":"cakes","product_ids":["cake00KA001685"]}'
```

Optionally add visual interpretations. The safe default does not replace existing
values:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/admin/catalogue/visual-interpretations/import `
  -H "Content-Type: application/json" `
  -d '{"category":"cakes","model_name":"Qwen3.8-Max","replace_existing":false,"items":[{"product_id":"cake00KA001685","visual_interpretation":"Pastel floral birthday cake"}]}'
```

Build incremental Dense vectors and fully rebuild that category's BM25 index:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/admin/catalogue/indexes/build `
  -H "Content-Type: application/json" `
  -d '{"category":"cakes","rebuild":false}'
```

Set `rebuild` to `true` to recreate the category Qdrant collection and regenerate
every active vector. Check index coverage with:

```powershell
curl.exe http://127.0.0.1:8000/api/v1/admin/catalogue/cakes/health
```

## Runtime API

Smart Shopping:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/recommendations `
  -H "Content-Type: application/json" `
  -d '{"request_type":"product_recommendation","message":"I need a romantic birthday cake under Rs. 7000"}'
```

Gift Box Builder:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/recommendations `
  -H "Content-Type: application/json" `
  -d '{"request_type":"gift_box","message":"Make it romantic","workflow_context":{"recipient":"girlfriend","theme":"romantic","item_count":4,"budget_min_lkr":12000,"budget_max_lkr":16000}}'
```

The backend creates `session_id` on the first valid turn; reuse it on follow-ups.
Every call receives a separate `request_id`. Recommendation cards contain exactly
`product_id`, `name`, live `price_lkr`, live-response `image_url`, `vendor`, and an
evidence-grounded `reason`.

## V1 Limitations

- Sessions are process-local and in memory; a future store can implement the same
  abstraction without changing workflow contracts.
- Admin routes intentionally have no authentication in this architecture phase.
- Catalogue refresh is explicit through the import APIs; BM25 uses full per-category
  rebuilds.
- Delivery validation is request-level because the current MCP contract does not
  guarantee per-product delivery eligibility.
- Live external integration tests require real OpenAI, Qdrant, and Kapruka MCP
  configuration and are not run by the credential-free test suite.
- The remote Kapruka MCP endpoint is rate-limited to 60 requests per minute per IP;
  the adapter applies a matching process-local request limiter.
