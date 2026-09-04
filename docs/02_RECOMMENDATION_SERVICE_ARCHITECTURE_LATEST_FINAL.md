# GenieAI Recommendation Service
## 02 — Recommendation Service Architecture

**Project:** GenieAI  
**Subsystem:** Recommendation Service  
**Status:** **FINAL — Step 2 Architecture Baseline**  
**Scope:** Internal architecture of the Python Recommendation Service  
**Primary consumers:** Smart Shopping, Gift Box Builder

---

# 1. Purpose

This document defines what happens inside the GenieAI Recommendation Service from the moment a valid request arrives from Next.js until the service returns a recommendation, clarification, workflow-mismatch, delivery-unavailable, or temporary-unavailable response.

The Recommendation Service is a reusable, category-independent Python backend. It is not the entire GenieAI backend.

Its primary responsibility is:

> Given the active GenieAI workflow, the user's current message, relevant recommendation-session context, and any workflow-specific preferences, identify, verify, rank, select, and explain the most appropriate Kapruka products.

---

# 2. Core Architectural Principles

1. **Next.js owns the active workflow.**
   - Smart Shopping → `product_recommendation`
   - Gift Box Builder → `gift_box`

2. **The original user query is preserved.**
   Semantic meaning is not replaced by a simplified pre-retrieval preference object.

3. **Hard constraints are separated by enforcement type.**
   - Stable deterministic constraints → pre-retrieval filtering
   - Volatile constraints → live MCP verification
   - Mandatory semantic requirements/exclusions → semantic verification/reranking

4. **Kapruka MCP is the live commerce source of truth.**
   Stored price/stock snapshots are never authoritative for final recommendations.

5. **Dense + BM25 hybrid retrieval is used.**
   Results are fused with Reciprocal Rank Fusion (RRF).

6. **Retrieval produces candidates; reranking decides relevance.**

7. **LLMs do not enforce deterministic bundle constraints.**
   Gift Box bundle selection is handled by deterministic Python optimization.

8. **The Recommendation Orchestrator coordinates the pipeline.**
   Specialized components remain independent and testable.

9. **All LLM-based decision stages use bounded retries, structured validation, and configured fallback models.**

10. **The frontend receives presentation-ready results, not internal recommendation-engine state.**

11. **Gift Box-specific context resolution is isolated from the shared recommendation core.**
   Gift Box fields such as recipient, theme, item count, and budget range are resolved by a Gift Box-specific context component rather than being added to the shared Query Understanding contract.

---

# 3. Final End-to-End Pipeline

## 3.1 Common Entry Path

```text
Next.js
   ↓
API Security Layer                    [designed later]
   ↓
Request Validation
   ↓
Create request_id / trace_id
   ↓
Load or Create Recommendation Session
   ↓
Gift Box request?
   ├── YES → Gift Box Context Resolver
   └── NO  → continue
        ↓
Query Understanding
   ↓
Workflow mismatch?
   ├── YES → workflow_mismatch response
   └── NO
        ↓
Clarification required?
   ├── YES → clarification response
   └── NO
        ↓
Delivery request present?
   ├── YES → Request-Level Delivery Validation
   │             ├── unavailable/unverifiable → stop gracefully
   │             └── available → continue
   └── NO
        ↓
Recommendation Planning
   ↓
Category-Specific Hybrid Retrieval
   ↓
Live Kapruka MCP Verification
   ↓
Reranking / Semantic Eligibility
   ↓
Branch by request_type
```

## 3.2 Smart Shopping Branch

```text
Verified + reranked candidates
        ↓
Cross-category ranking if needed
        ↓
Final Selection — up to 12
        ↓
Product Card Assembly
        ↓
Response Generation
        ↓
Update compact recommendation session
        ↓
Return response to Next.js
```

## 3.3 Gift Box Branch

```text
Verified + relevance-scored candidates
        ↓
Preserve category identity
        ↓
Bundle / Constraint Optimizer
        ↓
Final valid product combination
        ↓
Product Card Assembly
        ↓
Response Generation
        ↓
Update workflow-specific session state
        ↓
Return response to Next.js
```

---

# 4. Request Validation

Request Validation is deterministic and runs before any LLM, retrieval, or MCP work.

## 4.1 Required Fields

Every request must contain:

- valid `request_type`
- non-empty string `message`

Initial request types:

```text
product_recommendation
gift_box
```

## 4.2 Session ID

`session_id` is optional for the first turn.

If absent:

```text
valid new request
    ↓
backend creates session_id
    ↓
session_id returned to frontend
```

Follow-up turns reuse the same session ID.

## 4.3 Strict Validation

The service must reject:

- unsupported `request_type`
- non-string message values
- empty / whitespace-only messages
- malformed payloads
- messages above the configured maximum length
- unknown fields that are not part of the defined request schema

An LLM must never be used to repair malformed API input.

## 4.4 Workflow-Specific Structured Input

Because Gift Box Builder collects structured preferences, the final API schema must support a validated workflow-specific context object.

Conceptually:

```json
{
  "request_type": "gift_box",
  "session_id": "xyz789",
  "message": "Make it romantic.",
  "workflow_context": {
    "recipient": "girlfriend",
    "theme": "romantic",
    "item_count": 4,
    "budget": 15000
  }
}
```

The exact fields belong to the later API Specification. The principle is fixed:

> The request schema is strict, but it may contain a known, typed `workflow_context` for the active workflow.

For `gift_box` requests, this structured context is consumed by the Gift Box Context Resolver. Gift Box-specific fields must not be added to the shared Query Understanding output contract.

## 4.5 Authentication Boundary

Authentication / authorization is a separate API-security concern and is not part of recommendation-input validation.

---

# 5. Workflow Authority and Mismatch Handling

## 5.1 Frontend Tab Is Authoritative

The Recommendation Service does not normally infer the main workflow using an LLM.

```text
Smart Shopping tab   → product_recommendation
Gift Box Builder     → gift_box
```

The default GenieAI chat space is Smart Shopping.

## 5.2 No Silent Workflow Switching

If the user clearly requests another workflow, the backend must not silently change the active workflow.

Example:

```text
Current request_type:
product_recommendation

Message:
"Build a gift box for my girlfriend."
```

Conceptual response:

```json
{
  "type": "workflow_mismatch",
  "message": "This request is better suited to the Gift Box Builder.",
  "suggested_workflow": "gift_box",
  "recommendations": []
}
```

Next.js decides whether that becomes a message, highlighted tab, button, or other navigation UI.

---

# 6. Session / Recommendation Context

## 6.1 Frontend Message Pattern

The normal follow-up request should be:

```text
session_id + new_message
```

rather than:

```text
entire raw conversation + new_message
```

## 6.2 Compact Recommendation State

The backend maintains recommendation-specific state such as:

- current recommendation intent
- active workflow
- category scope
- stable constraints
- volatile constraints
- mandatory semantic requirements
- mandatory semantic exclusions
- previous recommendation product IDs
- referenced/selected products when needed
- compact recommendation summary
- workflow-specific state

The full raw GenieAI transcript may be stored elsewhere if the wider application needs it.

## 6.3 Follow-Up Resolution

Example:

```text
Previous:
"I need a romantic birthday cake for my girlfriend."

Follow-up:
"Show me cheaper ones."
```

The backend reuses prior state and applies the new price intent.

Other supported context-dependent references include:

```text
"Exclude the first one."
"More like number 3."
"Only show Cinnamon Grand now."
```

## 6.4 Context Reset

A message such as:

```text
"Forget those. Now I need flowers for my mother."
```

may reset the active recommendation context.

## 6.5 Unknown / Expired Session

If the session is unavailable:

- self-contained new message → process normally
- context-dependent message → ask clarification

## 6.6 Session Store

The architecture depends on a `Session Store` abstraction.

Redis is a likely production implementation, but the technology is not finalized in Step 2.

Session state has a TTL. Exact TTL is deferred.

## 6.7 Workflow State Separation

One session infrastructure may contain logically separate states:

```text
session
├── product_search_state
└── gift_box_state
```

## 6.8 Live Data Is Not Durable Session Truth

Current price and stock must not become long-lived session state.

## 6.9 Persistence Timing

The Orchestrator persists meaningful state updates after a successfully processed turn, including clarification state or newly returned recommendation IDs.

A temporary infrastructure failure must not overwrite the last known valid recommendation context with corrupted or incomplete state.

---

# 7. Query Understanding

## 7.1 Responsibility

Query Understanding:

1. preserves the original user query
2. determines category scope
3. extracts stable hard constraints
4. extracts volatile hard constraints
5. extracts soft numeric constraints where appropriate
6. identifies mandatory semantic requirements
7. identifies mandatory semantic exclusions
8. extracts request-level delivery context
9. detects clarification requirements
10. detects a clear workflow mismatch

It does **not** infer the active workflow under normal operation because `request_type` comes from Next.js.

It also does **not** own Gift Box-specific fields such as:

- recipient
- theme
- item count
- Gift Box budget range

Those belong to the Gift Box Context Resolver.

## 7.2 Original Query Preservation

For:

```text
"I need a romantic birthday cake for my girlfriend under Rs. 7000."
```

the full sentence remains the semantic retrieval query.

Query Understanding must not replace it with:

```json
{
  "style": "romantic",
  "occasion": "birthday",
  "recipient": "girlfriend"
}
```

for retrieval purposes.

Those meanings remain in the original text.

## 7.3 Gift Box Context Resolver

The Gift Box Context Resolver is a workflow-specific component and is not part of shared Query Understanding.

It runs only when:

```text
request_type = gift_box
```

Its responsibility is to resolve Gift Box-specific values from:

```text
typed workflow_context
+
current user message
+
gift_box_state from the session
```

Current Gift Box-specific fields include:

- `recipient`
- `theme`
- `item_count`
- `budget_min_lkr`
- `budget_max_lkr`

The resolver may reuse values already stored in `gift_box_state` and may extract missing values from the current message when appropriate.

If required Gift Box information is still insufficient after resolution, the workflow returns a clarification response rather than pushing Gift Box-specific interpretation into the shared Query Understanding component.

Smart Shopping does not depend on this component and does not consume Gift Box-specific fields.

If the resolver uses an LLM for any decision, it must follow the same bounded retry, structured-output validation, and fallback-model policy used by other LLM decision stages.

---

# 8. Query Understanding Output Contract

Conceptually:

```json
{
  "original_query": "I need a romantic cake delivered to Kandy tomorrow, under Rs. 7000, but no dark-looking ones.",

  "category_scope": {
    "mode": "single_category",
    "categories": ["cakes"],
    "user_explicit": true
  },

  "stable_constraints": {
    "vendor": null,
    "exact_weight_kg": null,
    "excluded_vendors": [],
    "excluded_product_ids": []
  },

  "soft_constraints": {
    "target_weight_kg": null
  },

  "volatile_constraints": {
    "min_price": null,
    "max_price": 7000,
    "requires_in_stock": true
  },

  "mandatory_semantic_requirements": [],

  "mandatory_semantic_exclusions": [
    "dark-looking"
  ],

  "delivery_request": {
    "city": "Kandy",
    "delivery_date": "2026-09-03"
  },

  "clarification": {
    "required": false,
    "reason": null,
    "missing_information": []
  },

  "workflow_mismatch": {
    "detected": false,
    "suggested_workflow": null
  }
}
```

This is an architectural contract, not the final Pydantic model.

## 8.1 No Generic LLM Confidence Score

Do not include uncalibrated values such as:

```json
{ "confidence": 0.91 }
```

as control signals in V1.

---

# 9. Constraint Policy

## 9.1 Stable Deterministic Constraints

Examples:

- explicit category
- vendor
- excluded vendor
- specific product ID / exclusion
- exact weight when reliable structured metadata exists

These may be used before retrieval.

## 9.2 Volatile Hard Constraints

Current volatile fields:

- price
- stock / availability

These must be enforced using live Kapruka MCP data.

## 9.3 Availability

All final recommendations must be currently in stock.

`requires_in_stock = true` is implicit even if the user does not mention stock.

## 9.4 Weight

Default interpretation:

```text
"I need a 1 kg cake."
→ approximate target
```

Only explicit wording such as:

```text
"exactly 1 kg"
```

becomes a hard exact-weight constraint.

## 9.5 Mandatory Semantic Requirements

Examples:

```text
"only red"
"must look romantic"
```

These are eligibility requirements evaluated using semantic / visual evidence.

## 9.6 Mandatory Semantic Exclusions

Examples:

```text
"no dark-looking cakes"
"not overly romantic"
```

A clear semantic violation makes the product ineligible; it is not merely a small score penalty.

## 9.7 Deterministic vs Semantic Exclusion

```text
"Don't show Java products."
→ deterministic metadata exclusion

"No dark-looking cakes."
→ semantic exclusion
```

They remain separate because they are enforced differently.

## 9.8 Ingredient / Allergen Limitations

Requirements such as:

- eggless
- nut-free
- gluten-free
- vegan

must not be guaranteed unless authoritative product data explicitly supports them.

Absence of an ingredient in the description does not prove absence from the product.

---

# 10. Clarification Policy

Clarify only when the current request lacks enough information for meaningfully targeted recommendation retrieval.

## 10.1 Clarification Required

Examples:

```text
"I need a cake."
"I need a gift."
```

Also clarify when:

- hard constraints contradict each other
- a context-dependent reference cannot be resolved
- ambiguity materially changes retrieval
- the request cannot be interpreted safely without guessing

## 10.2 Clarification Question Style

Ask a small related batch, normally 2–3 questions.

Example:

```text
"Who is the gift for, what is the occasion, and roughly what budget do you have?"
```

Avoid both:

- one-question-at-a-time interrogation
- long form-like questionnaires

## 10.3 Optional Information

These are useful but not individually mandatory:

- budget
- occasion
- recipient

Example:

```text
"I need something romantic for my girlfriend."
```

contains enough semantic intent to proceed even without a budget or occasion.

## 10.4 Context-Aware Clarification

```text
"Show me cheaper ones."
```

with valid session context → proceed.

Without usable session context → clarify.

---

# 11. Request-Level Delivery Validation

## 11.1 Current Capability

The current Kapruka MCP supports general city/date delivery validation but does not reliably provide true per-product delivery eligibility.

Therefore:

> Delivery is a request-level validation, not a product-level retrieval filter.

## 11.2 Flow

```text
delivery_request exists
        ↓
validate city + date through Kapruka MCP
        ↓
available?
   ├── yes → continue retrieval
   └── no  → stop before retrieval
```

If delivery validation itself cannot be trusted because the external service is unavailable, fail closed for a request that explicitly depends on that delivery requirement.

## 11.3 User Response

Do not expose technical details.

Conceptually:

```json
{
  "type": "delivery_unavailable",
  "message": "Delivery is not available for that location and date. Please choose another date or location.",
  "recommendations": []
}
```

If the MCP later supports true product-level delivery checking, delivery eligibility may become a volatile product-level constraint.

---

# 12. Recommendation Planning

The Planner creates retrieval instructions but does not execute retrieval.

## 12.1 Implementation Style

```text
deterministic logic first
        ↓
lightweight LLM only when semantic category selection is needed
```

Any LLM planning decision follows the global retry/fallback model policy.

## 12.2 Explicit Single Category

```text
"I need a romantic birthday cake."
→ search cakes only
```

## 12.3 Open Multi-Category Request

```text
"I need something romantic for my girlfriend."
```

The planner selects normally **3–5 semantically relevant categories**, not every Kapruka category.

## 12.4 Explicit Multiple Categories

```text
"I need a cake and flowers."
```

Both categories become mandatory retrieval targets.

## 12.5 Separate Retrieval Plan per Category

Conceptually:

```json
{
  "retrieval_plans": [
    {
      "category": "cakes",
      "query": "I need something romantic for my girlfriend.",
      "candidate_limit": 20,
      "stable_filters": {}
    },
    {
      "category": "flowers",
      "query": "I need something romantic for my girlfriend.",
      "candidate_limit": 20,
      "stable_filters": {}
    }
  ],
  "allow_expansion": true
}
```

The original full query is preserved for every selected category.

## 12.6 Initial Candidate Depth

Initial fused candidate target:

```text
20 candidates per category
```

Retrieval expansion is permitted later when necessary.

---

# 13. Retrieval Architecture

## 13.1 Hybrid Retrieval

Every category search uses:

```text
Dense retrieval
+
BM25 retrieval
        ↓
Reciprocal Rank Fusion (RRF)
```

## 13.2 Query Usage

Dense:
- embed the original full user query

BM25:
- use the original full query
- only basic lexical normalization

## 13.3 Stable Filters Before Retrieval

Stable filters are applied before candidate selection when reliable metadata exists.

Example:

```text
vendor = Cinnamon Grand
        ↓
retrieve only eligible Cinnamon Grand products
```

This avoids wasting candidate positions on products that must later be removed.

## 13.4 Volatile Values Are Not Pre-Filters

Price and stock are not authoritative Qdrant/BM25 filters.

They are checked live later.

## 13.5 Category-Specific Indexes

Each retrieval plan searches the corresponding category retrieval boundary.

Conceptually:

```text
cakes plan
├── cakes vector collection/index
└── cakes BM25 index

flowers plan
├── flowers vector collection/index
└── flowers BM25 index
```

Step 2 assumes category-separated retrieval indexes. Exact Qdrant collection schema/topology is finalized in Data Architecture.

## 13.6 Internal Retrieval Depth

Initial design:

```text
Dense Top 40
+
BM25 Top 40
        ↓
RRF
        ↓
Top 20 fused candidates per category
```

Exact depths remain configurable.

## 13.7 Deduplication

Duplicate Dense/BM25 hits are consolidated by canonical `product_id`.

## 13.8 Retrieval Scores

Dense/BM25/RRF evidence is retained internally but does not directly determine the final recommendation list.

## 13.9 No Universal Similarity Threshold

Do not hard-code a universal cosine cutoff in V1.

Thresholds may be introduced only after evaluation.

## 13.10 Expansion

Controlled candidate expansion:

```text
20 → 40 → 60
```

The Orchestrator requests expansion when too few valid/relevant products survive downstream stages.

Search depth must increase correspondingly rather than repeatedly returning the same candidate set.

---

# 14. Cross-Category Retrieval Behavior

## 14.1 Smart Shopping

Keep category candidate groups separate through retrieval and initial live verification.

Do not blindly compare raw scores from different category collections.

```text
category candidates
        ↓
live verification
        ↓
common cross-category reranker
        ↓
unified final shopping ranking
```

## 14.2 Gift Box Builder

Preserve category identity for bundle optimization.

```text
per-category candidates
        ↓
verification
        ↓
relevance scoring
        ↓
Bundle Optimizer
```

Do not flatten them into a normal Top-12 list.

---

# 15. Live Kapruka MCP Verification

## 15.1 Live Fields Used

The same `kapruka_get_product()` response is reused for both live commerce verification and primary product-card image metadata.

Extract:

- `price` — authoritative live commerce value
- `in_stock` — authoritative live commerce value
- primary image URL, normally `images[0]` — presentation metadata only

Only `price` and `in_stock` participate in volatile constraint validation.

The image URL is carried forward with the verified candidate for later product-card assembly. It is not used for recommendation constraints, Dense embeddings, Qdrant payloads, or BM25.

## 15.2 Verify Every Candidate Reaching the Stage

Every retrieved candidate that survives stable filtering is live-verified before reranking.

## 15.3 Concurrency

Verification calls should be concurrent with a configurable bounded concurrency limit.

## 15.4 Stock Rule

```text
in_stock = false
→ eliminate candidate
```

## 15.5 Price Rule

User price constraints are enforced using the current live price.

```text
max_price = 7000
live_price = 7200
→ eliminate
```

## 15.6 Individual Failure

If one product cannot be verified while the service is otherwise healthy:

```text
drop that candidate
continue
```

Log the failure internally.

## 15.7 Widespread Failure

If live verification is broadly unavailable:

```text
fail closed
```

Do not return potentially stale recommendations.

User-facing wording remains non-technical.

## 15.8 Short-Lived Cache

A brief verification cache may be used for price/stock to reduce repeated calls.

TTL is intentionally short and finalized later.

## 15.9 Qdrant Snapshot Policy

Stored price/stock snapshots may exist for diagnostics or ingestion history but are not authoritative.

## 15.10 Expansion

If too few valid products remain:

```text
verify initial candidates
        ↓
insufficient
        ↓
retrieve expansion
        ↓
verify only newly introduced candidates
```

---

# 16. Reranking and Semantic Eligibility

## 16.1 Reranker Input

The reranker evaluates:

- original full query
- product name
- product description
- visual interpretation, when available
- category
- vendor
- live price
- weight/size where relevant
- mandatory semantic requirements
- mandatory semantic exclusions
- retrieval evidence as supporting signals

Visual interpretation is optional enrichment. Its absence is not a pipeline failure and must not make an otherwise indexed product ineligible. When visual evidence is unavailable, the reranker uses the remaining supported product evidence and must not invent unsupported visual attributes.

## 16.2 Retrieval Evidence

Dense/BM25/RRF signals may support reranking but are not the primary decision authority.

## 16.3 Semantic Eligibility

The reranker must determine whether explicit mandatory semantic rules are satisfied.

Conceptual internal result:

```json
{
  "product_id": "cake123",
  "eligible": true,
  "relevance_score": 0.88,
  "semantic_requirement_failures": [],
  "semantic_exclusion_violations": []
}
```

`relevance_score` is an internal ranking value, not necessarily a calibrated probability.

## 16.4 Single-Category Smart Shopping

Rank verified eligible candidates and select up to 12.

## 16.5 Multi-Category Smart Shopping

Use one common reranker to compare candidates across categories against the same user intent.

This common stage is what makes cross-category comparison meaningful.

## 16.6 Soft Diversity

Broad Smart Shopping results should avoid unnecessary category repetition where equally relevant alternatives exist.

Diversity is soft:

> relevance wins over quota-filling.

## 16.7 Hard Constraints Cannot Be Reintroduced

The reranker cannot restore:

- over-budget products
- unavailable products
- excluded vendors/products
- other deterministic hard-constraint violations

## 16.8 Expansion After Reranking

If too few sufficiently relevant products remain, the Orchestrator may request deeper retrieval.

Never add clearly irrelevant products merely to hit 12.

## 16.9 Model Selection

The exact reranking model is selected later by benchmark using:

- recommendation quality
- semantic reasoning
- use of visual interpretations when available
- latency
- cost
- throughput
- structured-output reliability

---

# 17. Bundle / Constraint Optimizer

The Bundle Optimizer is used by Gift Box Builder.

It is deterministic Python logic, not an LLM.

## 17.1 Input

Only products that have already passed:

```text
retrieval
→ live verification
→ relevance reranking/scoring
```

## 17.2 Gift Box Rules

```text
Gift Box rules
      ↓
Bundle Optimizer
```

## 17.3 Hard Constraints

When applicable:

- total budget
- exact item count
- explicitly required categories
- user exclusions
- all products must be live-verified

Example:

```text
budget = 15000
bundle = 15500
→ invalid
```

## 17.4 Approximate Item Count

```text
"exactly 4 items"
→ hard count = 4

"around 4 items"
→ flexible count
```

Tolerance is finalized later.

## 17.5 Required Categories

A bundle missing an explicitly required category is invalid.

Do not silently substitute another category unless the user allows substitution.

## 17.6 Soft Objectives

The optimizer may maximize a combination of:

- candidate relevance
- useful category/product diversity
- sensible budget utilization

Budget utilization does **not** mean spending every rupee.

## 17.7 No Valid Bundle

If no combination satisfies all hard constraints:

```text
return no bundle
→ ask user to relax/adjust constraints
```

Do not manufacture a violating solution.

## 17.8 Auditable Output

Conceptually:

```json
{
  "selected_product_ids": ["P1", "P5", "P9", "P12"],
  "total_price": 14200,
  "item_count": 4,
  "constraints_satisfied": true,
  "required_categories_satisfied": true
}
```

Internal diagnostics may record objective components and rejection reasons.

## 17.9 Algorithm

Exact algorithm is deferred.

Possible implementation strategies include:

- combinatorial search
- knapsack-style optimization
- integer programming
- bounded heuristic search

The selected method must remain deterministic and auditable.

---

# 18. Final Recommendation Selection

## 18.1 Smart Shopping Count

Target:

```text
up to 12 products
```

If only 8 strong valid products exist, return 8.

Never weaken quality to force 12.

## 18.2 Ordering

Final order follows reranker order, with only approved soft-diversity adjustments for broad multi-category shopping.

## 18.3 Gift Box Count

Gift Box Builder does not follow the Smart Shopping Top-12 rule.

Their final product count is determined by optimizer constraints and workflow configuration.

---

# 19. Product Card Assembly

No additional Kapruka product lookup is required after final selection solely to obtain the primary product image.

The live verification call has already returned:

```text
price
in_stock
primary image URL
```

The verified candidate therefore carries the presentation metadata required for the V1 product card.

## 19.1 Product Images

GenieAI does not store product image binaries.

Images remain owned and served by Kapruka.

## 19.2 Image URL

The primary image URL is extracted from the same `kapruka_get_product()` response used for live price/stock verification, normally from:

```text
images[0]
```

It is presentation metadata only.

It must not be included in Dense embedding text, Qdrant payloads, or BM25 documents.

## 19.3 Product Card Assembly Flow

```text
live-verified candidate
(price + in_stock + image_url already attached)
        ↓
reranking / final selection
        ↓
combine with canonical name/vendor + verified live price/image_url
        ↓
response generation
        ↓
frontend product card
```

## 19.4 Missing Image

Because `image_url` is required by the V1 product-card contract, a selected product without a usable primary image should be replaced by the next already-valid candidate when possible.

Returning fewer valid products is preferable to emitting a malformed product card.

A widespread inability to obtain required product-card image metadata from the live MCP responses becomes a controlled service failure.

---


# 20. Response Generation

Response Generation explains already-selected products. It does not select products.

## 20.1 Input Scope

Provide only:

- original / resolved user intent needed for wording
- final selected products
- verified presentation fields
- evidence required for explanations

Do not provide the entire rejected candidate pool.

## 20.2 Per-Product Reason

Each recommended product receives a short evidence-grounded reason.

Example:

```text
"Matches your romantic birthday theme because of its rose decoration and elegant visual style."
```

Do not invent unsupported attributes.

## 20.3 Overall Message

Return one conversational message before the product cards.

## 20.4 Internal Scores

Do not expose:

- Dense score
- BM25 score
- RRF score
- reranker score
- internal constraint diagnostics

These remain available for logs/evaluation.

---

# 21. Response Envelope Families

The exact API schema is deferred, but the same endpoint should support structured response types.

## 21.1 Recommendation

```json
{
  "type": "recommendation",
  "session_id": "abc123",
  "message": "I found several strong matches.",
  "result_status": "success",
  "recommendations": []
}
```

## 21.2 Limited Results

```json
{
  "type": "recommendation",
  "result_status": "limited_results",
  "message": "I found 8 strong matches that meet your requirements.",
  "recommendations": []
}
```

## 21.3 Clarification

```json
{
  "type": "clarification",
  "message": "Who is the gift for, what is the occasion, and roughly what budget do you have?",
  "recommendations": []
}
```

## 21.4 Workflow Mismatch

```json
{
  "type": "workflow_mismatch",
  "message": "This request is better suited to the Gift Box Builder.",
  "suggested_workflow": "gift_box",
  "recommendations": []
}
```

## 21.5 Delivery Unavailable

```json
{
  "type": "delivery_unavailable",
  "message": "Delivery is not available for that location and date.",
  "recommendations": []
}
```

## 21.6 Temporary Unavailable

```json
{
  "type": "temporary_unavailable",
  "message": "I'm unable to confirm suitable products right now. Please try again shortly.",
  "recommendations": []
}
```

Exact field names and HTTP status behavior belong to the API Specification.

---

# 22. Recommendation Orchestrator

A central Orchestrator coordinates the complete pipeline.

It owns:

- stage ordering
- workflow-specific component invocation
- short-circuit decisions
- retrieval expansion
- fallback boundaries
- failure propagation
- branch selection by request type
- session load/persist timing
- final response path

It does **not** implement:

- semantic interpretation
- Gift Box context resolution
- Dense search
- BM25
- MCP parsing
- reranking
- bundle optimization
- response wording

This prevents a "god class."

---

# 23. Short-Circuit Behavior

## 23.1 Request Validation Failure

Stop before all model/retrieval work.

## 23.2 Workflow Mismatch

Return mismatch response.

## 23.3 Clarification

Return clarification response; do not retrieve.

## 23.4 Contradictory Constraints

Stop and ask user to clarify/relax.

## 23.5 Delivery Unavailable

Stop before product retrieval.

## 23.6 No Valid Products / Bundle

Do not violate hard constraints.

Return a natural response asking the user to adjust the request.

---

# 24. Failure Handling

## 24.1 Structured Internal Failure Categories

Initial taxonomy:

```text
INVALID_REQUEST
WORKFLOW_MISMATCH
CLARIFICATION_REQUIRED
DELIVERY_UNAVAILABLE
DELIVERY_VALIDATION_UNAVAILABLE
RETRIEVAL_FAILURE
LIVE_PRODUCT_VERIFICATION_UNAVAILABLE
RERANKER_FAILURE
BUNDLE_NO_SOLUTION
PRESENTATION_ENRICHMENT_FAILURE
LLM_DECISION_FAILURE
INTERNAL_ERROR
```

Exact taxonomy may evolve.

## 24.2 Normal Multi-Category Partial Failure

If one non-mandatory category fails but trustworthy results remain from others, Smart Shopping may continue.

Log the partial failure.

## 24.3 Mandatory Bundle Category Failure

Gift Box flows must not silently omit a required category.

Fail bundle construction or ask for adjusted requirements.

## 24.4 Reranking Failure

Do not silently downgrade to raw RRF order.

Use configured fallback reranker model(s).

If the fallback chain fails, return a controlled temporary failure.

---

# 25. LLM Retry and Fallback Model Policy

Any LLM-based **decision stage** must support:

1. bounded retry of transient failure
2. output-schema validation after every attempt
3. configured fallback model(s)
4. graceful failure only after the fallback chain is exhausted

Current examples:

- Query Understanding
- Gift Box Context Resolver, if implemented with an LLM
- semantic category selection in Recommendation Planning
- reranking / semantic eligibility
- future LLM-based decision components

Conceptual flow:

```text
Primary model
    ↓
validate
    ↓ invalid/transient failure
bounded retry
    ↓ still failed
Fallback model 1
    ↓
validate
    ↓ still failed
Fallback model 2 (optional)
    ↓
controlled failure
```

Every fallback implements the same component contract.

Architecture must remain model/provider independent.

---

# 26. External Retry Policy

External systems such as:

- Kapruka MCP
- LLM providers
- other future dependencies

use:

- explicit timeouts
- bounded retries
- backoff where appropriate

Permanent schema or validation failures are not retried blindly.

Exact retry counts/timeouts are deferred.

---

# 27. Observability and Traceability

Every request receives a unique `request_id` / trace ID.

The same ID follows the full pipeline.

Recommended diagnostics include:

```text
request_type
query_understanding_ms
planning_ms
dense_retrieval_ms
bm25_retrieval_ms
mcp_verification_ms
reranking_ms
bundle_optimization_ms
presentation_enrichment_ms
response_generation_ms
total_request_ms

retrieved_candidates
verified_candidates
semantic_eligible_candidates
final_recommendation_count
retrieval_expansion_count
category_failures
fallback_model_used
```

Technical details remain internal.

---

# 28. Data Responsibility Summary

## 28.1 Recommendation Index / Qdrant

Qdrant is the derived Dense retrieval index.

Each category uses its own collection.

The V1 vector configuration is:

```text
embedding model = OpenAI text-embedding-3-small
dimension = 1536
distance = Cosine
```

The Qdrant point payload is intentionally minimal:

```text
product_id
vendor
weight_kg
content_hash
```

`content_hash` is the SHA-256 hash of the exact Dense embedding text and supports incremental vector regeneration.

Qdrant does **not** store the canonical product description, visual interpretation text, price, stock, or image URL in its payload.

Category identity is implied by the selected category collection.

Qdrant does not own live commerce truth.

## 28.2 BM25 Index

BM25 is a separate category-specific lexical index outside Qdrant.

V1 uses `bm25s` persistence under:

```text
data/bm25/{category}/
```

BM25 source text uses trusted lexical product fields only and excludes visual interpretations, image URLs, live price, and live stock.

## 28.3 Kapruka MCP

Authoritative live source for:

- current price
- current stock / availability

Also provides the primary image URL in the same live product response used for price/stock verification; that image URL is carried forward as presentation metadata.

Current delivery capability supports request-level city/date validation rather than guaranteed product-level delivery eligibility.

## 28.4 Session Store

Stores compact recommendation context.

Does not store current price/stock as long-lived truth.

---

# 29. Synchronous API Model for V1

From the frontend perspective:

```text
Next.js request
        ↓
complete recommendation pipeline
        ↓
complete response
```

V1 does not require a background-job architecture.

If measured latency later demands streaming or asynchronous processing, that is a separate architecture change.

---

# 30. Decisions Explicitly Deferred

The following are intentionally **not** finalized in Step 2:

- exact FastAPI endpoint paths
- exact request/response Pydantic models
- authentication mechanism
- exact Session Store technology
- session TTL
- RRF constant
- exact retrieval source depths during expansion
- reranker model
- planner model
- fallback-model order
- response-generation model
- concurrency limit for MCP verification
- retry counts / timeout values
- verification-cache TTL
- image/presentation-cache TTL
- similarity / relevance thresholds
- soft-diversity algorithm
- bundle optimizer algorithm
- optimizer objective weights
- approximate item-count tolerance
- approximate weight tolerance
- detailed Gift Box rule schema
- logging / metrics / tracing technology
- deployment topology

These decisions belong to later Data, API, Evaluation, Security, and Production Implementation architecture phases.

---

# 31. Step 2 Final Architecture Status

The internal Recommendation Service architecture is now defined across:

- Request Validation
- Workflow Authority
- Session / Recommendation Context
- Query Understanding
- Gift Box Context Resolver
- Hard / Soft / Semantic Constraint Policy
- Clarification
- Request-Level Delivery Validation
- Recommendation Planning
- Dense + BM25 Hybrid Retrieval
- RRF Fusion
- Stable Pre-Retrieval Filtering
- Live Kapruka MCP Verification
- Reranking / Semantic Eligibility
- Cross-Category Smart Shopping Ranking
- Bundle / Constraint Optimizer
- Final Selection
- Product Card Assembly
- Response Generation
- Pipeline Orchestration
- Failure Handling
- LLM Retry / Fallback Policy
- Traceability / Observability

> **Step 2 is complete and frozen as the current architecture baseline.**

Changes to these decisions should be made deliberately through an architecture update rather than implicitly during implementation.

---

# 32. Next Architecture Phase

The next architecture phase should define **Product Data Architecture and Database Design**.

It should specify:

- complete product data lifecycle from Kapruka MCP to recommendation indexes
- canonical product record
- product ID strategy
- category taxonomy
- Qdrant collection topology
- BM25 index schema/lifecycle
- visual interpretation storage
- embedding input construction
- stable vs volatile data ownership
- any relational/configuration database requirements
- session-store requirements
- cache responsibilities
- ingestion/update/reindex strategy
