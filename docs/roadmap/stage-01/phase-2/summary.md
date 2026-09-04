# Phase 2 — Catalogue data & ingestion (admin side)

**Goal:** An admin types a motorcycle name and ends up with an approved catalogue entry — sourced documents, verified specifications, an image — without leaving the browser.

## Delivered

- **Catalogue data model** — four tables (models, source documents, specifications, images) with a legal status-transition matrix; approval promotes the draft spec to verified and approves pending images in one transaction.
- **Admin API** — a small in-house JSON:API layer (envelopes, pagination, filters, stable error codes) carrying products, operations, documents and images; every route admin-only, every write CSRF-guarded.
- **Background worker** — Taskiq/Redis worker service running ingestion and embedding jobs, separate from the web process and never running migrations.
- **Ingestion pipeline** — Wikipedia first (matched title recorded so the admin sees what was matched), then web search candidates, fetched and converted to Markdown, plus one image downloaded into three WebP sizes served from `/media`.
- **Live progress** — an operations table records every job's status/progress/message; PostgreSQL notifications fan out over a single server-sent-events stream so the backlog list updates without polling or reloads.
- **Spec extraction** — an LLM (OpenRouter via LangChain) fills a draft spec from the ingested text; unit-normalising validators convert hp/lbs and discard implausible values.
- **Knowledge base** — heading-aware chunking of every document plus 1536-dimension embeddings recorded per chunk with their model name; a rebuild CLI re-embeds the catalogue after a model change.
- **Admin backlog screen** — status chips, URL-persisted filter, add-model dialog, live progress cell, retry on failure, stream-disconnect warning.
- **Admin review screen** — three tabs (rendered source documents with provenance, editable draft-spec form, image with attribution) plus approve/reject with confirmation dialogs.
- **Operator CLI** — per-stage commands (`probe`, `fetch-url`, `fetch-image`, `run`, `extract-specs`, `chunks rebuild`, `embeddings rebuild`, `operations demo`, `llm ping`) so every stage is testable without the UI.
- **Acceptance run** — the end-to-end script executed in a real browser with screenshots, including failure path and security spot-checks (non-admin, missing CSRF, uncookied stream).

## Non-obvious decisions

- **Frontend built against stub hooks first, then swapped wholesale at two sync points** — both tracks ran in parallel; a swap requiring component changes was treated as a broken contract and reported, not patched. Both swaps landed with zero component changes.
- **Server-sent events, not polling** — one stream per logged-in session; on reconnect the client blanket-refreshes because events during the gap are lost. Events carry ids only (under 1 KB), never payloads.
- **Notify only after commit** — a state change costs two commits (data, then announcement), because a notification is delivered only when its own transaction commits.
- **Admins edit the draft spec only; the UI never writes verified values** — approval is the sole promotion path, which keeps a hand-corrected value auditable against the extracted one.
- **Partial source failures are warnings, not failures** — a missing image, absent search key or failed extraction still reaches review, where the admin can correct manually; only zero usable documents fails the run. Network-caused emptiness is retried instead.
- **Retry is a plain status change, not an action endpoint** — setting a model back to "ingesting" re-enqueues server-side, so the API stays resource-shaped.
- **Structural chunking only, no semantic/LLM chunking** — heading-aware splitting is cheap, deterministic and gives every chunk a citable heading path.
- **OpenRouter-only, enforced as a rule** — if OpenRouter could not serve a capability the step was to stop and report rather than wire a second provider; embeddings therefore run through OpenRouter's OpenAI-compatible route.
- **Every extraction field declared as required in the schema, optionality expressed as "or null"** — upstream providers reject a JSON schema whose required list is incomplete; this kept the intended structured-output method rather than falling back to function calling.
- **Two tooling constraints absorbed rather than worked around** — a Redis client default silently killed the worker every 5 idle seconds (fixed by one socket setting, not by pinning an older Redis); the Markdown splitter chain needed a line-break repair between its two stages so stored chunk text stays byte-identical to the source.
- **Re-ingestion is a fresh run** — the previous documents, image and files are deleted first, so a retry never mixes two runs.
- **Live LLM verification was blocked for much of the phase** (no API key in the environment) and was closed later by a live fix run; embeddings and extraction were provably keyless-degrading in the meantime.

## Not delivered / deferred

- **Web-search-sourced documents in the acceptance run** — no search API key at the time; demonstrated Wikipedia-only with the pinned warning. A second search provider (OpenRouter web plugin) was added as a follow-up.
- **Manufacturer as a first-class entity** — stayed a free-text column; became the Phase 2b interlude.
- **Retrieval and the advisor** — chunks and embeddings land here, all retrieval logic is Phase 3.
- **Path-traversal hardening of raw-file storage** — unreachable today (server-minted ids); regression tests exist, guard deferred to the Phase 5.1 validation sweep.
- **Image replacement by upload** — explicitly out of scope; admins can only reject.
- **Stuck-job reaping** — a permanently unreachable network leaves a model in "ingesting" until an operator intervenes.
- **Polish items filed from the acceptance run** — stray table separator in Wikipedia infobox Markdown, image chip not refreshing on approve, dev-only blank image previews in the cross-origin setup; all deferred to Phase 5.
