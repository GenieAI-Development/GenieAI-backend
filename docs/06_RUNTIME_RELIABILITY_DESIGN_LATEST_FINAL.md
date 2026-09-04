# GenieAI — Step 6: Runtime Recommendation Workflow Reliability

## 1. Purpose

This document defines the production reliability policy for GenieAI's runtime recommendation workflow.

The goal is to ensure that AI decisions are validated, failures are handled predictably, hard constraints are never violated, live commerce data is treated safely, and failed requests do not corrupt session state.

---

## 2. Shared Reliability Wrapper for LLM Decision Stages

Every LLM-based decision component must use the same reliability pattern.

This applies to:

```text
Query Understanding
Gift Box Context Resolver
Category / Recommendation Planning
Reranking
Future LLM decision stages
```

Required execution pattern:

```text
Primary model
→ validate structured output
→ bounded retry on transient or invalid-output failure
→ configured fallback model(s)
→ validate output again
→ controlled failure only after all attempts fail
```

Rules:

- Every structured LLM output must be validated before downstream use.
- Malformed or incomplete LLM output must never continue through the pipeline.
- Retries must be bounded.
- Fallback models must follow the same output contract as the primary model.
- If all attempts fail, the request must enter a controlled failure path.

---

## 3. Retrieval Degradation Policy

The normal retrieval strategy is:

```text
Dense Retrieval + BM25 Retrieval
→ Reciprocal Rank Fusion (RRF)
```

If only one retrieval component fails, GenieAI may continue in a safe degraded mode:

```text
Dense unavailable → use BM25 only
BM25 unavailable → use Dense only
```

The degraded execution must be logged internally.

If both retrieval systems fail:

```text
response_type = temporary_unavailable
HTTP 503
```

This allows the system to remain available when one retrieval mechanism experiences a temporary failure without hiding a complete retrieval outage.

---

## 4. Live Kapruka Verification Policy

Live Kapruka verification remains strict because final price and stock must be current.

For each retrieved candidate:

```text
kapruka_get_product()
→ extract live price
→ extract live in_stock
→ extract primary image URL (normally images[0])
```

Only `price` and `in_stock` are authoritative volatile commerce-verification values.

The primary image URL is presentation metadata carried forward for the final product card; it does not participate in constraint validation.

If verification fails for an individual product:

```text
drop candidate
→ continue with remaining candidates
```

If Kapruka MCP verification is broadly unavailable or there are not enough reliably verified candidates:

```text
response_type = temporary_unavailable
HTTP 503
```

Rules:

- Do not perform an additional MCP product lookup solely to obtain the primary image URL after final selection.
- Never present cached or indexed stock as current stock.
- Never present stale price snapshots as authoritative current prices.
- A broad live-verification failure must not be disguised as product scarcity.

---

## 5. Product Scarcity vs System Failure

GenieAI must distinguish a valid but constrained catalogue result from an infrastructure or AI-system failure.

### Valid Scarcity

If the pipeline executes successfully but only a limited number of products satisfy the user's constraints:

```text
response_type = limited_results
```

Example:

```text
User requests an exact 1 kg cake below a tight budget,
and only three verified products satisfy all constraints.
```

This is a real recommendation result.

### System Failure

If the system has too few results because of failures such as:

```text
retrieval outage
Kapruka MCP outage
model failure
reranker failure
```

then the response must be:

```text
response_type = temporary_unavailable
```

The system must never represent infrastructure failure as genuine product scarcity.

---

## 6. Reranking Reliability

Normal flow:

```text
Hybrid retrieval
→ live verification
→ semantic reranking
→ final selection
```

If the primary reranker fails:

```text
bounded retry
→ fallback reranker model(s)
```

If every reranker attempt fails:

```text
response_type = temporary_unavailable
```

Rules:

- Reranking must not silently disappear.
- GenieAI must not silently return raw RRF rankings when the reranking stage is expected.
- Recommendation quality must not change unpredictably because of an unreported reranker failure.

---

## 7. Gift Box Optimizer Reliability

Gift Box bundle construction remains deterministic.

LLMs may interpret user intent and score semantic relevance, but the final bundle is produced by deterministic application logic.

Flow:

```text
retrieved candidates
→ live-verified candidates
→ relevance scores
→ deterministic bundle / constraint optimizer
```

The optimizer must enforce hard constraints such as:

```text
budget bounds
exact item count when required
required categories
product exclusions
verified availability
```

Rules:

- Never construct a bundle that violates a hard constraint.
- Never allow an LLM to override deterministic bundle constraints.
- If no valid bundle exists, GenieAI should ask the user to relax an appropriate constraint rather than inventing a solution.

---

## 8. Session State Consistency

Session state must only be updated using validated and resolved information.

Required pattern:

```text
user input
→ validation
→ resolution
→ successful state update
```

Do not persist:

```text
malformed LLM output
failed extraction results
invalid Gift Box constraints
partially processed request state
unvalidated intermediate values
```

A failed request must not corrupt or overwrite previously valid session state.

This applies especially to:

```text
product_search_state
gift_box_state
```

---

## 9. Request Traceability and Observability

The already-finalized identifiers remain:

```text
session_id → conversation
request_id → individual API request / turn
```

Every runtime request must be traceable internally using `request_id`.

Recommended internal logging fields include:

```text
pipeline stage
stage duration
primary model used
retry attempts
fallback model attempts
retrieval candidate counts
retrieval degraded-mode status
MCP verification success/failure counts
reranker outcome
final result count
response_type
failure category
```

These details belong in internal logs and observability systems, not in the user-facing API response.

The purpose is to support:

- production debugging;
- recommendation-quality analysis;
- failure diagnosis;
- latency analysis;
- model/fallback monitoring.

---

## 10. Final Runtime Reliability Philosophy

The runtime workflow follows this principle:

```text
Validate AI decisions
        ↓
Gracefully degrade where safe
        ↓
Fail closed where correctness depends on live data
        ↓
Never silently reduce recommendation quality
        ↓
Never violate hard constraints
        ↓
Never corrupt session state
```

---

## 11. Final Step 6 Rules

The production reliability baseline is:

1. All LLM decision stages use validated retries and fallback models.
2. Retrieval may degrade to Dense-only or BM25-only if one retriever fails.
3. Live Kapruka price and stock verification remains strict.
4. Real product scarcity and system failure are represented differently.
5. Reranking must retry/fallback and must never silently disappear.
6. Gift Box bundle construction remains deterministic and constraint-safe.
7. Session state is updated only from validated/resolved information.
8. Every request is traceable internally through `request_id`.

These rules define the V1 runtime reliability architecture for GenieAI.
