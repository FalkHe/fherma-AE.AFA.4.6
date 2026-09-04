# Phase 3 — Retrieval, the advisor agent & the consultation UI

**Goal:** Make the advisory brain work end-to-end and let a customer hold the whole consultation in the browser.

## Delivered
- **Persistent consultations** — chats, messages and preferences tables (one migration) with soft delete, server-generated titles from the first customer message, and firmness-tagged preferences that supersede rather than overwrite when a customer changes their mind.
- **Chat API** — `chats` and `chat-messages` resources on the existing JSON:API layer, session-cookie auth, CSRF on writes, wrong-owner/unknown/deleted all answering 404 (no existence leak), and a frozen message-part contract (tool calls, sources, recommendations) that both tracks built against in parallel.
- **Background reply pipeline** — replies are produced by a worker job behind an operation record, so a long turn never blocks the request; the customer always gets something back (an apologetic message on failure, never a dead chat).
- **Advisor speaks first** — creating a consultation immediately queues a greeting plus the opening interview question, like a salesperson in a store.
- **Hybrid retrieval** — one SQL statement fusing keyword search and vector similarity (reciprocal-rank fusion) over approved models only, every result carrying its source document, title, URL and heading path.
- **Query translation** — an LLM pass turning conversational language ("1.65 m, just got my A2, city commuting") into up to three rewritten search queries plus typed spec filters, resolved against verified specs.
- **RAG pipeline** — translation → candidate shortlist → multi-query retrieval → second fusion pass, returning the "why these sources" payload; degrades to raw-utterance search instead of failing.
- **Eight advisor tools** — catalogue search, spec comparison, licence/fit check, cost estimator, knowledge retrieval, preference capture, unknown-bike flagging, recommendation presentation; each with a CLI harness for direct inspection.
- **Advisor agent loop** — a staged interview (experience → licence → use case → budget → physique → preferences) over a tool-calling loop with a step cap and a 120 s turn timeout; every executed call, source and recommendation is persisted with the message.
- **Consultation UI** — list and chat views with markdown replies, seen/typing states over server-sent events, delete-with-confirm, four labelled tool-result renderers plus a generic fallback, a collapsible de-duplicated sources section, and recommendation cards with images and key specs.
- **Resumability without checkpoints** — closing the browser mid-turn and reopening shows the reply; a killed worker heals server-side after a stale window and the next message completes.
- **Repeatable evidence** — a scripted 8-turn interview over the real HTTP API asserting greeting-first, ≥3 distinct tool calls, approved-only recommendations, attached sources, exactly one backlog row, and identical history for a second session; reused by later phases.

## Non-obvious decisions
- **Soft delete, no restore UI** — deleted consultations stay in the database for auditability but are indistinguishable from non-existent ones over the API.
- **Two model knobs** — the advisor gets its own `ADVISOR_MODEL`; extraction and query translation keep the cheaper utility model. Interview quality is tuned by changing an `.env` value, not code.
- **Hand-rolled tool loop, no agent framework** — no LangGraph, no prebuilt executor, no checkpointer: resumability comes from the persisted conversation, so a framework would add a dependency and a second source of truth.
- **Recommendations arrive as a tool call**, not a second structured-output pass — one mechanism, no post-hoc parsing of prose.
- **Writes by the agent are a closed list** (record preference, flag unknown bike, present recommendations) — low-risk and product-approved; any further write tool needs an owner decision.
- **A missing spec is never guessed** — a filter on an unverified value excludes the bike, fit rules answer "unknown", and cost lines are omitted with the gap named in the assumptions, because a confident wrong number is worse than a gap.
- **Cost estimates use a versioned in-code coefficient table**, not a pricing API, and label themselves as estimates with visible assumptions in the UI.
- **Filters that match nothing return nothing** — the pipeline does not silently widen the search, which would cite bikes the customer already ruled out.
- **Typing indicator reads only the chat's own pending-turn pointer**, never the admin operations endpoint (which has no ownership column and must stay admin-only).
- **Exactly one optimistic update in the whole app** — the customer's outgoing message; failed sends keep the typed text with retry/discard rather than dropping it.
- **Full conversation replay as agent context** (message bodies only, no past tool traffic); a rolling summary was rejected until token limits actually bite.
- **Tool arguments are camelCase via an explicit schema hand-off** — the tool library silently drops field aliases otherwise, which would have made the model emit unusable argument names.
- **Backlog dedup is by catalogue slug only** — a differently spelled mention can create a redundant backlog row, accepted because fuzzy matching needed a database extension the phase's single-migration rule forbade; the cost is one row an admin discards.
- **Prompt tuning replaced code changes** for three live agent failures found during UI wiring (invented bike ids, judging named models from memory, empty result sets), and unknown-bike flagging was made consent-gated (offer first, flag only after a yes).
- **Mobile overflow is verified by measurement, not by eye** — three separate bugs (wide comparison tables, long chat titles, unbreakable tool output) all pushed the whole page sideways at phone width.

## Not delivered / deferred
- **Concurrent-turn 409 race** — two truly simultaneous sends can both be accepted; unreachable through the UI. Routed to Phase 4 as step 4.5, then dropped there: the planned fix provably cannot close the race, and any working fix breaks a Phase-3 contract. Owner decision still open.
- **Verified purchase prices** — no approved model had a verified price, so cost estimates and budget filters had no price data. Plausible-but-unverified demo prices were seeded in Phase 4; real price research is still outstanding.
- **Recommendation card links** — cards are non-interactive; the link to the model detail page was wired in Phase 4 once the catalogue pages existed.
- **Prompt-injection hardening, tracing and error-surface polish** — only baseline hygiene here (retrieved content framed as untrusted); the full sweep, Langfuse tracing and error-boundary work went to Phase 5.
- **Admin app-bar overflow at 390 px** — pre-existing, not a Phase-3 regression; fixed in Phase 4 and re-verified in Phase 5.
- **A1 licence class** — deliberately omitted; the catalogue carries no verified A1 equivalent to the A2 eligibility flag.
- **Language support beyond English** — retrieval keyword search is English-only by design; no language detection.
