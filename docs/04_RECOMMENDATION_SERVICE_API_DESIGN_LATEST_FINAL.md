# Step 4 — Recommendation Service API Design

## 1. Purpose

This document defines the production-facing runtime API contract between the GenieAI Next.js frontend and the Python FastAPI Recommendation Service.

Step 4 covers the **runtime recommendation API only**. Admin/data-management APIs for catalogue ingestion, visual-interpretation import, index building, and catalogue health are intentionally handled separately.

The Recommendation Service currently supports exactly two workflows:

- **Smart Shopping** → `product_recommendation`
- **Gift Box Builder** → `gift_box`

`event_planning` is not part of the current GenieAI Recommendation Service scope.

---

## 2. Runtime Endpoint

Use one primary runtime endpoint for both supported workflows:

```http
POST /api/v1/recommendations
```

The frontend-selected workspace/tab determines `request_type` and is authoritative.

The backend may detect that the user's message appears better suited to the other workflow, but it must not silently switch workflows. Instead it returns a structured `workflow_mismatch` response.

Allowed `request_type` values:

```text
product_recommendation
gift_box
```

---

## 3. Request Identity

### 3.1 `session_id`

`session_id` identifies one multi-turn GenieAI conversation.

Rules:

- The frontend omits `session_id` on the first request of a new conversation.
- The backend generates an opaque UUID-style session identifier.
- The backend returns the generated `session_id` in the response.
- The frontend reuses that same `session_id` for later turns.
- The frontend never generates its own `session_id`.
- The frontend sends the new user message, not the entire conversation history.

If the frontend provides an unknown or expired `session_id`:

- if the current message is self-contained, the backend may create a new session and continue;
- if the message depends on missing previous context, the backend returns a clarification response.

The API does not expose session timestamps in normal responses.

### 3.2 `request_id`

Every runtime API call receives a unique backend-generated `request_id`.

`request_id` is never supplied by the frontend.

Meaning:

```text
session_id = whole conversation
request_id = one API request / conversational turn
```

`request_id` is returned on responses and used for backend tracing, observability, and debugging.

---

## 4. Common Request Contract

### Smart Shopping

```json
{
  "request_type": "product_recommendation",
  "session_id": "optional-existing-session-id",
  "message": "I need a romantic cake under Rs. 6000"
}
```

### Gift Box Builder

```json
{
  "request_type": "gift_box",
  "session_id": "optional-existing-session-id",
  "message": "Build something romantic for my girlfriend",
  "workflow_context": {
    "recipient": "girlfriend",
    "theme": "romantic",
    "item_count": 4,
    "budget_min_lkr": 12000,
    "budget_max_lkr": 16000
  }
}
```

---

## 5. Top-Level Request Validation

The runtime request accepts only the documented fields.

Unknown top-level fields are rejected deterministically.

### `request_type`

Required.

Allowed values:

```text
product_recommendation
gift_box
```

Any other value is a schema-validation error.

### `message`

Required.

Validation:

- must be a string;
- trim surrounding whitespace;
- must not be empty or whitespace-only;
- maximum length: **2000 characters**.

### `session_id`

Optional.

When provided, it must conform to the backend's expected opaque session identifier format.

### `workflow_context`

Workflow-dependent.

- For `gift_box`: optional typed object.
- For `product_recommendation`: must be omitted.

If `workflow_context` is supplied with Smart Shopping, the request is rejected rather than silently ignored.

---

## 6. Gift Box `workflow_context`

The V1 Gift Box request supports exactly these optional fields:

```json
{
  "recipient": "girlfriend",
  "theme": "romantic",
  "item_count": 4,
  "budget_min_lkr": 12000,
  "budget_max_lkr": 16000
}
```

Unknown fields inside `workflow_context` are rejected.

All fields are optional because Gift Box context may be gathered across multiple turns.

### 6.1 `recipient`

- optional string;
- trim whitespace;
- non-empty when provided;
- maximum 200 characters;
- structurally validated only;
- free text, not an enum.

Examples of valid values:

```text
girlfriend
mentor
mother
colleague
```

The API does not reject unusual recipients merely because their meaning is uncommon.

For matching and internal state purposes, the value is normalized case-insensitively. For example:

```text
" Girlfriend " → "girlfriend"
```

### 6.2 `theme`

- optional string;
- trim whitespace;
- non-empty when provided;
- maximum 200 characters;
- structurally validated only;
- free text, not an enum.

Examples:

```text
romantic
retro gaming
minimalist
luxury
```

The value is normalized case-insensitively before being persisted into Gift Box session state.

### 6.3 `item_count`

- optional integer;
- valid range: **1–10**;
- when explicitly provided through `workflow_context`, it means an **exact required item count**.

Flexible natural-language requests such as "around four items" remain in `message` and are interpreted by the Gift Box Context Resolver. V1 does not expose a separate public `item_count_mode` field.

### 6.4 `budget_min_lkr`

- optional integer;
- when provided, must be greater than `0`.

### 6.5 `budget_max_lkr`

- optional integer;
- when provided, must be greater than `0`.

### 6.6 Budget relationship

If both bounds are supplied:

```text
budget_max_lkr >= budget_min_lkr
```

Equality is valid.

Example:

```json
{
  "budget_min_lkr": 15000,
  "budget_max_lkr": 15000
}
```

A request may provide only one budget bound. The backend must not invent the missing bound.

The Bundle Optimizer applies whichever valid bound(s) are actually available.

---

## 7. Gift Box Context Resolver Boundary

Gift Box-specific context must remain outside the shared Recommendation Core.

For `request_type = gift_box`, a dedicated **Gift Box Context Resolver** combines:

1. the latest explicit information in the current user message;
2. the current request's typed `workflow_context`;
3. existing `gift_box_state` from the session.

Conflict precedence:

```text
newest explicit current-message value
    > current workflow_context value
    > existing gift_box_state value
```

The resolver produces clean normalized Gift Box state.

Example internal state:

```json
{
  "recipient": "girlfriend",
  "theme": "romantic",
  "item_count": 4,
  "budget_min_lkr": 12000,
  "budget_max_lkr": 16000
}
```

The raw `workflow_context` payload is **not** persisted directly. The session stores resolved/normalized `gift_box_state` instead.

Omitted fields keep their previous state values.

`null` is not treated as a special reset operation. Explicit null values are rejected by request validation.

A later valid value may override an older value normally.

Example:

```text
Earlier budget_max_lkr = 16000
User later explicitly says "make it under 20000"
→ resolved state updates budget_max_lkr to 20000
```

If an LLM is used inside the Gift Box Context Resolver, the system-wide LLM reliability policy applies: structured validation, bounded retries, configured fallback model(s), and controlled failure only after all attempts fail.

---

## 8. Minimum Gift Box Context Before Bundle Construction

The Gift Box workflow does not require every possible field to be known.

Before constructing a meaningful bundle, the resolved context should contain at least:

- some useful gifting intent: `recipient` **or** `theme`;
- a usable budget constraint: minimum, maximum, or both.

`item_count` is optional.

If important information is still missing, return a structured clarification response rather than guessing critical constraints.

---

## 9. Common Runtime Response Envelope

Both workflows use the same top-level response envelope:

```json
{
  "request_id": "req_abc123",
  "session_id": "session_xyz",
  "request_type": "product_recommendation",
  "response_type": "recommendation",
  "message": "Here are some romantic cakes within your budget."
}
```

### Field meanings

- `request_id` — identity of this API call.
- `session_id` — identity of the conversation.
- `request_type` — workflow selected by the frontend.
- `response_type` — outcome of the current request.
- `message` — friendly user-facing conversational text.

`request_type` and `response_type` are intentionally separate concepts.

The older generic field name `type` is not used.

---

## 10. Allowed `response_type` Values

V1 runtime outcomes:

```text
recommendation
limited_results
clarification
workflow_mismatch
delivery_unavailable
temporary_unavailable
```

These are recommendation-flow outcomes, not all HTTP errors.

---

## 11. Smart Shopping Success Response

A successful Smart Shopping response contains top-level `products` and `result_count`.

```json
{
  "request_id": "req_abc123",
  "session_id": "session_xyz",
  "request_type": "product_recommendation",
  "response_type": "recommendation",
  "message": "Here are some romantic cakes within your budget.",
  "result_count": 2,
  "products": [
    {
      "product_id": "cake00KA001685",
      "name": "Springtime Birthday Ribbon Cake",
      "price_lkr": 5770,
      "image_url": "https://...",
      "vendor": "Kapruka Cakes",
      "reason": "Its floral styling and soft colors make it a strong romantic choice."
    },
    {
      "product_id": "cake00KA001700",
      "name": "Example Cake",
      "price_lkr": 5900,
      "image_url": "https://...",
      "vendor": "Kapruka Cakes",
      "reason": "Its presentation matches the romantic theme while staying within budget."
    }
  ]
}
```

Architecture target: return up to **12** final Smart Shopping products.

---

## 12. Gift Box Success Response

A successful Gift Box response contains top-level `bundle` and does not expose another top-level `products` field.

```json
{
  "request_id": "req_def456",
  "session_id": "session_xyz",
  "request_type": "gift_box",
  "response_type": "recommendation",
  "message": "I created a romantic four-item gift box within your budget.",
  "bundle": {
    "products": [
      {
        "product_id": "cake00KA001685",
        "name": "Springtime Birthday Ribbon Cake",
        "price_lkr": 5770,
        "image_url": "https://...",
        "vendor": "Kapruka Cakes",
        "reason": "The floral presentation fits the romantic theme."
      }
    ],
    "total_price_lkr": 15400,
    "item_count": 4
  }
}
```

The bundle has exactly these V1 fields:

```text
products
total_price_lkr
item_count
```

Do not repeat the requested budget range inside the returned bundle.

`bundle.item_count` is calculated by the backend from the actual selected products.

`bundle.total_price_lkr` is calculated by the backend from the selected products' live verified prices.

---

## 13. Product Card Contract

Every product returned by Smart Shopping or inside a Gift Box bundle has exactly these required V1 fields:

```text
product_id
name
price_lkr
image_url
vendor
reason
```

### `product_id`

Canonical Kapruka product identifier.

### `name`

Human-readable product name.

### `price_lkr`

Integer current price in Sri Lankan Rupees.

The live price returned by Kapruka verification is authoritative at recommendation time.

### `image_url`

Required for V1 product-card rendering.

Image URL is extracted from the same `kapruka_get_product()` response already used for live price/stock verification, normally from the primary image (`images[0]`).

The image URL is carried forward with the verified candidate; no additional MCP lookup is required after final selection solely to obtain it.

If a selected candidate cannot provide the required image, the service should use another valid candidate when possible. Returning fewer valid products is preferable to emitting a malformed product card.

### `vendor`

Human-readable vendor name.

Do not expose internal `vendor_id` in the V1 runtime response.

### `reason`

Required short explanation of why the selected product fits the user's request.

Rules:

- generated only after final product selection;
- grounded in available product/request evidence;
- concise;
- target maximum approximately 200 characters;
- must not invent unsupported attributes.

### Fields intentionally excluded

The V1 product card does not expose:

- category;
- vendor_id;
- internal retrieval scores;
- Qdrant metadata;
- BM25 scores;
- stale price snapshots;
- stock internals;
- model/reranker details.

---

## 14. `limited_results`

`limited_results` is a separate response type.

It means the service found valid results that satisfy the enforced constraints, but could not reach the normal target quantity or coverage.

### Smart Shopping

Return the valid products that were found:

```json
{
  "request_id": "req_1",
  "session_id": "session_1",
  "request_type": "product_recommendation",
  "response_type": "limited_results",
  "message": "I found a few options that match all of your requirements.",
  "result_count": 3,
  "products": []
}
```

### Gift Box

If a valid but reduced/limited bundle exists under the workflow's accepted constraints, return the actual bundle with `response_type = limited_results`.

The service must never violate hard constraints merely to avoid `limited_results`.

---

## 15. Clarification Response

If the recommendation cannot responsibly continue because important information is missing or unresolved:

```json
{
  "request_id": "req_2",
  "session_id": "session_1",
  "request_type": "gift_box",
  "response_type": "clarification",
  "message": "What budget would you like me to use for the gift box?",
  "missing_fields": [
    "budget_max_lkr"
  ]
}
```

`missing_fields` is always included for clarification responses.

Initial controlled `missing_fields` vocabulary:

```text
recipient
theme
item_count
budget_min_lkr
budget_max_lkr
category
occasion
delivery_city
delivery_date
```

For Smart Shopping, these values may act as structured frontend hints even when they are not all literal top-level request fields.

Do not return empty `products` or `bundle` fields merely as placeholders on a clarification response.

---

## 16. Workflow Mismatch Response

When the selected frontend workflow does not match what the user's current request appears to require, the backend does not silently switch workflows.

Example:

```json
{
  "request_id": "req_3",
  "session_id": "session_1",
  "request_type": "product_recommendation",
  "response_type": "workflow_mismatch",
  "message": "It looks like you're trying to build a gift box. I can help with that in the Gift Box Builder.",
  "suggested_workflow": "gift_box"
}
```

`suggested_workflow` appears only for `workflow_mismatch`.

Allowed values follow the supported workflow names.

Do not include empty product or bundle result fields.

---

## 17. Delivery Unavailable Response

Delivery validation is request-level, not a claim of per-product delivery eligibility.

If an explicitly delivery-dependent request cannot be fulfilled because the requested delivery city/date is not supported:

```json
{
  "request_id": "req_4",
  "session_id": "session_1",
  "request_type": "product_recommendation",
  "response_type": "delivery_unavailable",
  "message": "Delivery isn't available for the location or date you selected."
}
```

No empty result fields are included.

If delivery validation is required for the request but the live delivery dependency cannot be verified, the service follows the fail-closed reliability policy rather than claiming deliverability.

---

## 18. Temporary Unavailable Response

A real backend or critical dependency failure returns a nontechnical user-facing message.

Example:

```json
{
  "request_id": "req_5",
  "session_id": "session_1",
  "request_type": "gift_box",
  "response_type": "temporary_unavailable",
  "message": "I couldn't complete the recommendation right now. Please try again."
}
```

Do not expose infrastructure details such as:

- MCP failures;
- Qdrant failures;
- BM25 implementation;
- model names;
- reranker failures;
- stack traces;
- provider error payloads.

Detailed technical information belongs in backend logs and observability systems.

---

## 19. HTTP Status Policy

Normal conversational/recommendation outcomes use HTTP 200:

| Outcome | HTTP Status |
|---|---:|
| `recommendation` | 200 |
| `limited_results` | 200 |
| `clarification` | 200 |
| `workflow_mismatch` | 200 |
| `delivery_unavailable` | 200 |

Critical backend/dependency failure:

| Outcome | HTTP Status |
|---|---:|
| `temporary_unavailable` caused by backend/dependency failure | 503 |

Malformed or invalid API requests:

| Error | HTTP Status |
|---|---:|
| malformed JSON | 400 |
| deterministic schema validation failure | 422 |

Examples of `422` validation failures:

- unsupported `request_type`;
- missing `message`;
- whitespace-only `message`;
- message longer than 2000 characters;
- `item_count` outside 1–10;
- invalid budget bounds;
- explicit null Gift Box context values;
- unknown top-level fields;
- unknown Gift Box context fields;
- `workflow_context` supplied for Smart Shopping.

---

## 20. Validation Error Envelope

Do not expose FastAPI/Pydantic's raw default validation error body directly to the frontend.

Use a GenieAI-owned error contract.

Example:

```json
{
  "request_id": "req_error_123",
  "session_id": "session_xyz",
  "error": {
    "code": "INVALID_REQUEST",
    "message": "The request contains invalid fields.",
    "details": [
      {
        "field": "workflow_context.item_count",
        "issue": "must be between 1 and 10"
      }
    ]
  }
}
```

Rules:

- include `request_id` when the backend can generate one;
- include `session_id` only when the supplied session is a valid existing session;
- use frontend-friendly field names;
- include field-level details when applicable;
- do not expose implementation internals;
- retain detailed technical errors in logs.

---

## 21. Runtime State Ownership

The frontend is responsible for:

- selecting the workflow/tab;
- sending `request_type`;
- sending the latest user message;
- retaining and resending the backend-provided `session_id`;
- optionally supplying typed Gift Box `workflow_context` updates.

The Recommendation Service is responsible for:

- generating `session_id` and `request_id`;
- maintaining conversational session state;
- maintaining separate logical `product_search_state` and `gift_box_state` where required;
- resolving Gift Box context;
- determining whether clarification is required;
- running the shared recommendation pipeline;
- branching into Smart Shopping final selection or Gift Box bundle optimization;
- returning only frontend-ready structured results.

The frontend does not need to resend the full resolved Gift Box context on every turn.

---

## 22. Relationship to the Recommendation Architecture

The API contract intentionally preserves the architectural separation defined in Step 2.

Common Recommendation Core:

```text
Request Validation
    ↓
Session Load/Create
    ↓
Gift Box Context Resolver (gift_box only)
    ↓
Shared Query Understanding
    ↓
Recommendation Planning
    ↓
Category-specific Dense + BM25 Retrieval
    ↓
Live Kapruka Verification
    ↓
Reranking / Semantic Eligibility
```

Then branch:

```text
product_recommendation
    → final Top-N selection
    → product-card assembly
    → response


gift_box
    → deterministic Bundle/Constraint Optimizer
    → product-card assembly
    → response
```

Gift Box-specific rules must not leak into shared retrieval, Qdrant collections, BM25 indexing, live price/stock verification, or common reranking logic.

---

## 23. Reliability Rules Reflected by the API

The API must reflect the production reliability decisions from the Recommendation Service architecture:

- live price and stock are verified during recommendation time;
- the live verification response supplies `price`, `in_stock`, and the primary `image_url`; only `price` and `in_stock` are authoritative commerce-verification values, while `image_url` is presentation metadata;
- one candidate failing live verification may be dropped and replaced;
- widespread critical live-verification failure causes controlled failure rather than stale recommendations;
- reranker failure invokes configured fallback reranker model(s), not silent raw-RRF fallback;
- any LLM structured-decision stage uses validation, bounded retries, and configured fallback model(s);
- user-facing errors remain nontechnical.

---

## 24. V1 Non-Goals

The runtime recommendation endpoint does **not** define:

- product catalogue ingestion;
- visual-interpretation import;
- Qdrant index-building operations;
- BM25 rebuild operations;
- catalogue health/deactivation operations;
- checkout or order creation;
- full Kapruka product-detail APIs;
- frontend authentication implementation details;
- internal optimizer algorithm details;
- internal LLM prompt schemas;
- model-provider-specific error payloads.

These belong to separate implementation or API-design stages.

---

## 25. Final V1 Runtime Contract Summary

### Endpoint

```http
POST /api/v1/recommendations
```

### Supported workflows

```text
product_recommendation
gift_box
```

### Core request fields

```text
request_type
session_id (optional first turn)
message
workflow_context (gift_box only, optional)
```

### Gift Box workflow-context fields

```text
recipient
theme
item_count
budget_min_lkr
budget_max_lkr
```

### Common response fields

```text
request_id
session_id
request_type
response_type
message
```

### Result shape

```text
Smart Shopping → result_count + products
Gift Box      → bundle
```

### Product card

```text
product_id
name
price_lkr
image_url
vendor
reason
```

### Normal response types

```text
recommendation
limited_results
clarification
workflow_mismatch
delivery_unavailable
temporary_unavailable
```

This completes the **Step 4 Runtime Recommendation API design**. Minor internal state representation and optimizer implementation choices may be finalized during coding without changing this public API contract.
