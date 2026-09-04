# GenieAI Recommendation Service
## 01 — System Scope and Boundaries

**Project:** GenieAI  
**Subsystem:** Recommendation Service  
**Status:** Architecture Baseline — Step 1  
**Purpose:** Define the responsibilities, ownership boundaries, and integration scope of the GenieAI Recommendation Service before implementation begins.

---

## 1. System Context

GenieAI is an intelligent AI chatbot platform for Kapruka.com. It provides multiple AI-assisted shopping experiences, including:

- Product search and recommendation
- Gift box creation
- Product comparison
- Gift message generation

The Recommendation Service is not the entire GenieAI backend. It is a dedicated Python service responsible for product recommendation intelligence and is consumed by multiple GenieAI experiences.

---

## 2. Recommendation Service Mission

The Recommendation Service has one primary responsibility:

> Given a user's intent, preferences, constraints, and relevant conversation context, identify, verify, rank, and explain the most suitable Kapruka products.

The service must be reusable across different GenieAI workflows rather than being designed only for direct product search.

---

## 3. High-Level Platform Boundary

```text
                         GenieAI Platform
                               │
                     Next.js Application
                  (UI + high-level orchestration)
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
          Product Search              Gift Box Builder
                 │                           │
                 └─────────────┬─────────────┘
                               │
                               ▼
                ┌──────────────────────────┐
                │ Recommendation Service   │
                │        Python            │
                └──────────────────────────┘
                               │
                ┌──────────────┼───────────────┐
                │              │               │
          Query Understanding Retrieval     Reranking
                │              │               │
                └──────────────┼───────────────┘
                               │
                         Kapruka MCP
                       + Recommendation DBs
                               │
                               ▼
                   Verified Recommendations
```

Separate GenieAI capabilities may remain outside this Python service, for example:

```text
Next.js ──→ Gift Message Generation Model
Next.js ──→ Product Comparison
Next.js ──→ Cart / Order / Checkout Workflow ──→ Kapruka MCP
```

---

## 4. Responsibilities of the Python Recommendation Service

The Recommendation Service owns recommendation-related intelligence.

### 4.1 In Scope

The service is responsible for:

- Receiving recommendation requests from the GenieAI application
- Understanding natural-language shopping intent
- Detecting relevant product categories
- Extracting recommendation preferences and constraints
- Maintaining recommendation-specific conversation context
- Performing semantic retrieval
- Performing hybrid retrieval where applicable
- Searching recommendation data stored in Qdrant and supporting indexes
- Using enriched product information such as visual interpretations
- Retrieving candidate products
- Performing live product verification through Kapruka MCP
- Reranking candidate products
- Generating recommendation explanations
- Generating a conversational recommendation response
- Returning structured product recommendation data to the caller
- Supporting multiple product categories through one reusable architecture

---

## 5. Responsibilities Outside the Recommendation Service

The Recommendation Service should not become the entire GenieAI application backend.

### 5.1 Next.js Application

The Next.js application owns:

- User interface
- Chat interface
- Rendering recommendation messages
- Rendering product cards
- High-level GenieAI experience orchestration
- Invoking the Recommendation Service
- Other AI functions that do not require the recommendation engine
- Gift message generation
- Application-level navigation and user interaction

Additional backend capabilities may exist inside the Next.js application where appropriate.

### 5.2 Commerce / Ordering Workflow

Commerce operations must remain logically separate from recommendation logic.

Examples include:

- Add to cart
- Cart management
- Order creation
- Checkout
- Payment-related flow
- Delivery workflow

These operations may use Kapruka MCP, but they are not responsibilities of the Recommendation Service.

### 5.3 Product Comparison

Product comparison is considered a separate GenieAI capability.

It may consume recommendation results or product data, but it should not be tightly coupled to the core recommendation pipeline.

### 5.4 Gift Message Generation

Gift message generation may be handled by a different AI model or service through the Next.js application.

It does not belong inside the Recommendation Service.

---

## 6. Recommendation Service Consumers

The initial Recommendation Service must support multiple GenieAI experiences.

### 6.1 Product Search

Example:

```text
User:
"I need a romantic birthday cake for my girlfriend."
```

The Recommendation Service directly identifies suitable products.

### 6.2 Gift Box Creation

Example collected preferences:

```text
Recipient: Girlfriend
Theme: Romantic
Number of items: 4
Budget: LKR 15,000
```

The Gift Box Builder uses the same Recommendation Service to identify suitable products for the box.

The Gift Box Builder must not have its own separate recommendation engine.

---

## 7. Category Strategy

The architecture must support all Kapruka product categories from the beginning.

Examples include:

- Cakes
- Flowers
- Chocolates
- Gifts
- Food
- Perfumes
- Electronics
- Other Kapruka categories

However, the first fully populated and validated recommendation dataset may contain only the selected set of 642 cakes.

This means:

> The implementation may start with cakes, but the architecture must never assume that cakes are the only supported category.

Category-specific data, indexing strategies, prompts, or enrichment rules may exist where required, but they must operate inside a category-independent recommendation framework.

---

## 8. Kapruka MCP Boundary

Kapruka MCP is treated as the official source-of-truth interface for Kapruka commerce data available to GenieAI.

### 8.1 Kapruka MCP Responsibilities

Depending on the capabilities exposed by the MCP, it may provide:

- Product information
- Product availability
- Current price
- Delivery-related information
- Product lookup
- Ordering operations
- Other live commerce information

### 8.2 Recommendation Database Responsibilities

Recommendation databases exist to provide recommendation intelligence, not to replace Kapruka as the commerce source of truth.

Example recommendation data:

- Product ID
- Product description
- Visual interpretation
- Semantic representation
- Stable recommendation metadata
- Embeddings
- Search/indexing information

### 8.3 Source-of-Truth Principle

Volatile commerce data should not be trusted indefinitely from the vector database.

Conceptually:

```text
Qdrant / Recommendation Storage
    ↓
Find semantically relevant candidates

Kapruka MCP
    ↓
Verify live product information

Recommendation Pipeline
    ↓
Rank verified candidates
```

The exact stable-vs-volatile field design will be finalized in the Data Architecture phase.

---

## 9. Conversation Boundary

GenieAI should support conversational recommendation flows.

Example:

```text
User:
"I need a romantic birthday cake for my girlfriend."

GenieAI:
[recommendations]

User:
"Show me cheaper ones."
```

The second request must understand that "ones" refers to the previous recommendation context.

### 9.1 Current Frontend Behavior

The current frontend sends:

```text
new message
+
complete previous message history
```

for each request.

This may become inefficient because conversation history grows continuously and increases token usage.

### 9.2 Target Architecture

The Recommendation Service should eventually manage recommendation-specific conversation state.

Conceptual request:

```json
{
  "session_id": "abc123",
  "message": "Show me cheaper ones."
}
```

Possible backend state:

```text
session_id: abc123

current_intent:
    romantic birthday cake

constraints:
    recipient: girlfriend
    occasion: birthday
    max_price: 8000

previous_recommendations:
    [...]

conversation_summary:
    User is searching for a romantic birthday cake for their girlfriend.
```

The exact session-storage technology and memory strategy will be decided later.

Potential technologies such as Redis should not be considered finalized at this stage.

---

## 10. Recommendation Response Boundary

The Recommendation Service should return both:

1. A conversational response
2. Structured product recommendation data

Conceptual example:

```json
{
  "session_id": "abc123",
  "message": "These cakes are especially suitable for a romantic birthday celebration.",
  "recommendations": [
    {
      "product_id": "cake123",
      "name": "Romantic Rose Cake",
      "price": 6500,
      "reason": "Strong romantic visual theme with red roses."
    }
  ]
}
```

The Next.js application is responsible for presentation.

It should be able to render:

```text
Conversational AI message
+
Product cards
```

The final API schema will be designed in the API Specification phase.

---

## 11. Ordering Boundary

Recommendation and ordering are separate responsibilities.

Correct separation:

```text
Recommendation Service
        ↓
Returns suitable products
```

Then:

```text
User selects product
        ↓
Cart / Commerce Workflow
        ↓
Kapruka MCP
        ↓
Order / Checkout
```

The Recommendation Service may retrieve live product information through Kapruka MCP during recommendation generation, but it should not own cart or checkout state.

---

## 12. Core Architectural Principle

GenieAI must have **one reusable Recommendation Service**, not separate recommendation systems for each user experience.

```text
Product Search ────────┐
                       ├──→ Recommendation Service
Gift Box Creation ─────┘
```

These workflows provide different inputs and contexts, but they consume the same recommendation intelligence layer.

---

## 13. Service Identity

The Python project being designed is therefore defined as:

> **GenieAI Recommendation Service**

A reusable, category-independent Python recommendation backend consumed by multiple GenieAI shopping experiences.

It is not:

- The entire GenieAI backend
- The Next.js application
- A cake-only RAG application
- The shopping cart system
- The checkout system
- The gift-message generator

---

## 14. Initial Component Ownership

| Component / Capability | Primary Owner |
|---|---|
| User Interface | Next.js |
| Chat Interface | Next.js |
| High-level GenieAI orchestration | Next.js |
| Product recommendation intelligence | Python Recommendation Service |
| Query understanding for recommendations | Python Recommendation Service |
| Recommendation conversation context | Python Recommendation Service |
| Retrieval | Python Recommendation Service |
| Qdrant access | Python Recommendation Service |
| Recommendation reranking | Python Recommendation Service |
| Live candidate verification | Python Recommendation Service + Kapruka MCP |
| Recommendation explanation | Python Recommendation Service |
| Product search experience | Next.js + Recommendation Service |
| Gift box builder | Next.js + Recommendation Service |
| Gift message generation | Separate model / Next.js |
| Product comparison | Separate GenieAI capability |
| Cart management | Commerce workflow |
| Order creation | Commerce workflow + Kapruka MCP |
| Checkout | Commerce workflow / Kapruka |
| Live Kapruka commerce data | Kapruka MCP |

---

## 15. Decisions Finalized in Step 1

The following decisions are considered part of the architectural baseline:

1. The Recommendation Service will be implemented as a dedicated Python backend service.
2. The Recommendation Service is not the main backend for every GenieAI function.
3. Next.js remains responsible for the web application and high-level orchestration.
4. Product Search and Gift Box Creation will consume the same Recommendation Service.
5. Separate recommendation engines will not be created for these two workflows.
6. The architecture will support multiple Kapruka product categories from day one.
7. Cakes are the first populated recommendation dataset, currently using 642 selected cake products.
8. Kapruka MCP is the source-of-truth interface for live commerce information.
9. Recommendation databases provide recommendation intelligence and indexing, not authoritative live commerce state.
10. The Recommendation Service should support conversational recommendation flows.
11. Backend-managed recommendation state is preferred over repeatedly sending the complete conversation history.
12. The Recommendation Service should return both conversational text and structured product recommendations.
13. Cart, checkout, and order workflows remain outside the Recommendation Service.
14. Recommendation results may be live-verified against Kapruka MCP before being returned.

---

## 16. Intentionally Unresolved

The following decisions are deliberately deferred to later architecture steps:

- Exact internal recommendation pipeline
- Exact API endpoints
- Request and response schemas
- Qdrant collection strategy
- Whether one or multiple Qdrant collections should be used
- Supporting database technologies
- Redis or other conversation-state storage
- Session lifetime and memory strategy
- Embedding model configuration
- Hybrid retrieval implementation
- BM25 implementation
- Candidate pool size
- Filtering rules
- Reranking model
- MCP retry and failure strategy
- Caching
- Observability
- Authentication
- Deployment topology
- Evaluation metrics
- Cost and latency targets

These should not be implemented before their corresponding architecture decisions are finalized.

---

## 17. Next Architecture Step

The next document should define the **end-to-end internal architecture of the GenieAI Recommendation Service**.

It should answer:

> What happens internally from the moment the Recommendation Service receives a user request until verified and ranked recommendations are returned to the Next.js application?

This will become the basis for the Recommendation Pipeline architecture.
