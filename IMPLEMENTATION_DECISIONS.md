# Implementation Decisions

- 2026-09-03 / Plan 1: BM25 via `rank-bm25` + regex tokenizer; index built once per `ProductIndex`, never per query.
- 2026-09-03 / Plan 1: `ProductIndex.search(query, top_k, filters)` is the frozen retrieval interface; semantic/hybrid (Plan 4) must match it.
- 2026-09-03 / Plan 1: Baseline eval uses lexical Recall@K / Precision@K / MRR + constraint match; LLM-judged contextual metrics deferred to Plan 3 with this dataset reused unchanged.
- 2026-09-03 / Spec deviation logged: explicit `POST /orders` route reserved for Plan 3 (source describes ordering via checkout flow without naming the route).
- 2026-09-03 / Plan 2: Money math — free shipping at subtotal >= 5000 (empty cart ships 0), else flat 49; 18% GST on (subtotal + shipping); all totals rounded to 2 decimals.
- 2026-09-03 / Plan 2: Real LLM provider adapter deferred to Plan 3; `LLMClient` protocol + `FakeLLM` are the seam. Agent/tests/demo never touch the network.
- 2026-09-03 / Plan 2: Order idempotency keys live in `OrderService` memory; durable key store moves to Plan 3 with the DB-backed state.
- 2026-09-03 / Plan 2: Cart API surfaces one error type (`CartError`); unknown product on add raises `CartError`, not `ProductNotFound`.
