# GenieAI Recommendation Service — V2 Runtime

GenieAI is a FastAPI backend for Kapruka-style product recommendations. This document describes the **current runtime path** after simplifying the original pipeline for speed and reliability.

## What the runtime does

```text
POST /api/v1/recommendations
  -> validate request and create/reuse a session
  -> understand the search request and select a category
  -> create a search plan
  -> retrieve 60 candidates (Qdrant dense search + BM25, fused with RRF)
  -> read cached price, stock, and image data from Supabase
  -> apply price, availability, and image filters
  -> order by RRF retrieval score
  -> return up to 12 product cards
```

For a product recommendation, the response is built deterministically. It does not make an additional LLM call after retrieval.

## Runtime dependencies

- **OpenAI**: structured query understanding/planning and query embeddings.
- **Qdrant**: semantic (dense-vector) candidate retrieval.
- **BM25**: lexical candidate retrieval from `data/bm25/{category}`.
- **Supabase**: cached product commerce data used to filter and populate product cards.
- **Canonical catalogue JSON**: stable product metadata from `data/catalogue/{category}.json`.

The cache table defaults to `kapruka_gift_products`. For each candidate the backend reads `product_id`, `price_amount`, `in_stock`, `image_url`, and `images`.

## Features intentionally not in the product-recommendation runtime

- Live Kapruka MCP product verification.
- Kapruka delivery validation.
- Workflow-mismatch responses.
- Query-understanding clarification responses for incomplete product searches.
- LLM semantic reranking.
- LLM response/message generation after product search.
- Repeated retrieval/verification retries at wider candidate depths.

The related source modules may remain in the repository for future use, but they are disconnected from the normal product recommendation path.

Kapruka MCP is retained for catalogue ingestion/admin operations, not for normal product lookup requests.

## API

### Health

```powershell
curl.exe http://127.0.0.1:8000/healthz
```

Expected response:

```json
{"status":"ok"}
```

### Product recommendation

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/recommendations `
  -H "Content-Type: application/json" `
  -d '{"request_type":"product_recommendation","message":"Find a birthday cake under 7000 LKR"}'
```

The backend creates `session_id` when one is not supplied. Send it back on a follow-up request if conversation context is required.

Successful responses return `recommendation` when 12 products are available, or `limited_results` when fewer qualify. A `temporary_unavailable` response produces HTTP 503 and means an external dependency or the pipeline was unavailable.

Each product card contains:

```text
product_id, name, description, price_lkr, image_url, vendor
```

## Search and filtering behaviour

- The original message is used for dense and BM25 retrieval.
- The planner selects the applicable product category/collection.
- Retrieval is widened to **60 candidates** once; it does not retry with deeper pools.
- Supabase filters candidates using cached `in_stock`, price range, and a usable image. Its cached `description` is returned to the frontend as the product description.
- Missing Supabase records are skipped, not treated as a system-wide failure.
- Results are sorted by RRF score and the first 12 are returned.

Because prices and stock are cached, they are only as current as the latest cache-sync run.

## Configuration

Copy `.env.example` to `.env` and configure:

```dotenv
OPENAI_API_KEY=...
QDRANT_URL=...
QDRANT_API_KEY=...
SUPABASE_URL=...
SUPABASE_SECRET_KEY=...
SUPABASE_PRODUCT_TABLE=kapruka_gift_products
```

`NEXT_PUBLIC_SUPABASE_URL` is also accepted as an alias for `SUPABASE_URL`.

On Vercel, add the same values as Production environment variables. Local `.env` values are not deployed automatically.

## Run locally

Python 3.12 is required.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open the API documentation at `http://127.0.0.1:8000/docs`.

## Product-cache sync

The one-time/backfill script compares active canonical cake IDs with Supabase, fetches missing products through Kapruka MCP, and upserts the discovered cache records:

```powershell
.\.venv\Scripts\python.exe -m app.ingestion.sync_kapruka_gift_products --dry-run
.\.venv\Scripts\python.exe -m app.ingestion.sync_kapruka_gift_products
```

`fetched=<product-id>` only means that record was fetched in the current process. The database is changed when the script completes and prints its upsert summary.

## Vercel

`vercel.json` schedules `GET /healthz` every five minutes. This can reduce idle cold starts where the plan supports that schedule, but it is not a guarantee that a function instance remains warm.

Deploy after changing application code or Vercel environment variables.
