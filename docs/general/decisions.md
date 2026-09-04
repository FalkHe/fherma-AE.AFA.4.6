# Decisions

Choices that are not obvious from the code, recorded with their reason. Phase
narrative and superseded alternatives stay in
[`../roadmap/`](../roadmap/roadmap.md).

## Data and persistence

- **No ORM relationships anywhere.** Foreign keys plus explicit service lookups.
  Async lazy loading is a footgun; making every fetch explicit removes a whole
  class of `MissingGreenlet` bugs.
- **ULID primary keys, slugs as separate unique columns.** Sortable and opaque;
  a slug can change without breaking references.
- **Draft/verified spec split** — one `motorbike_specs` row per
  `(motorbike, kind)`. Extraction only ever writes `draft`; approval is the only
  writer of `verified`. Spec writes are **full-object**: an omitted field becomes
  NULL, which makes re-extraction idempotent by construction.
- **A rejected model is not terminal and nothing is deleted.** `rejected →
  ingesting` re-runs; documents, drafts and images are retained.
- **Every public service function commits.** Callers never manage transactions.
  The cost of this rule is the concurrent-turn race below.
- **`operations` is the only job state.** Taskiq runs with no result backend and
  only ids cross the process boundary, so the queue can never hold state the
  database does not.
- **State is committed before `pg_notify`.** Two commits per change, and a lost
  notification loses nothing.

## API

- **JSON:API 1.1 as a small internal layer**, not a framework — we needed the
  envelope and the error shape, not the ecosystem.
- **No relationships or `included`.** The include machinery was deferred and
  never turned out to be needed; the SPA fetches related resources by filter.
- **Clients branch on HTTP status plus `code`, never on detail text**, so detail
  strings stay free to change.
- **404, not 403, for a model a customer may not see.** A 403 would confirm the
  row exists.
- **All admin endpoints are admin-only including reads.** `manufacturers` was
  later relaxed to `current_user` because the customer catalogue needs the
  filter vocabulary.

## LLM

- **OpenRouter is the only gateway, always through LangChain.** A graded
  requirement, and provider routing/fallback is then OpenRouter's job rather
  than app-level failover.
- **Structured output uses `method="json_schema"`, not `strict`.** Two
  concessions live on that seam: every property is listed in `required` with
  null unions (OpenAI-compatible gateways demand it), and variant specs travel
  as `{key, value}` pairs and are reshaped back.
- **Extraction clamps implausible values to `None` instead of erroring.** A null
  field an admin fills is cheaper than a wrong field they must first notice.
- **Two model keys.** `ADVISOR_MODEL` tunes interview quality without touching
  extraction or query translation (`CHAT_MODEL`). Model ids are `.env` values,
  never hardcoded and never asserted in tests.
- **No LangGraph, no checkpointer.** The advisor is a hand-rolled `bind_tools`
  loop; resumability is the persisted chat history. A checkpointer would persist
  agent-internal mid-run state we do not want.
- **The three write tools run autonomously.** `record_preference`,
  `flag_unknown_bike` and `present_recommendations` are low-risk and scoped to
  the current chat; a permission prompt per preference would wreck the
  interview. `flag_unknown_bike` is consent-gated in the prompt instead. A
  fourth write tool needs an owner decision.
- **Recommendations arrive through a tool**, not a second structured-output
  pass over the reply, and are stored as a **write-time snapshot** so a card
  keeps rendering after the catalogue moves on.
- **Only `retrieve_bike_knowledge` fences its payload**, and only in the model
  view — persisted results stay unfenced so the UI shows clean text.

## Retrieval

- **Hybrid FTS + pgvector fused with RRF** (`RRF_K = 60`, 50 candidates per
  leg). Spec questions are lexical, "is it comfortable" is semantic; RRF needs
  no score normalisation between the two.
- **Filters are applied inside both legs**, never as a Python post-pass, so a
  scoped search still returns `limit` rows.
- **A NULL spec never matches a filter.** "Unknown" is not "0".
- **Query translation degrades silently.** A failed or empty translation falls
  back to the raw utterance, unscoped: worse retrieval beats a failed turn.
- **Filters that match nothing skip retrieval entirely** and return no chunks,
  which is what lets the advisor say "nothing matches, shall I widen it?"
- **English-only FTS** (`plainto_tsquery('english')`) — the corpus is English.
- **Structural chunking only.** Markdown headings then a recursive splitter;
  semantic chunking is cost without a demonstrated retrieval win here.

## Frontend

- **Server state lives only in TanStack Query**; SSE events invalidate it. No
  Redux/Zustand, no copying into component state.
- **Exactly one optimistic update** (the outgoing chat message). Everywhere else
  the round trip is fast enough that optimism would only add reconciliation
  bugs.
- **Filter state lives in the URL**, so a filtered catalogue is shareable and
  survives reload.
- **The server renders model names; the client never formats a saved name.**
  Ambiguity resolution needs the sibling set, which only the server has.
- **One Markdown renderer** (`UntrustedMarkdown`) for all three sites, adopted
  once the rule of three was reached.
- **Errors surface per screen** as an `EmptyState` with refetch — no snackbar
  infrastructure. The one exception is the admin backlog transition failure
  (a 6 s `Snackbar`), because that action has no screen of its own.

## Operations

- **The web container migrates, the worker never does.** One writer to the
  schema.
- **Raw fetched payloads are retained permanently.** Provenance means being able
  to show what we actually read.
- **`make langfuse-down` stops by service name.** `docker compose down -v` once
  destroyed the application database; `down` is never truly service-scoped.

## Open decisions

Owner input needed; each is documented as a known limitation in the meantime.

- **Concurrent-turn 409 race.** Two simultaneous message POSTs for one chat both
  succeed. A row lock is *provably insufficient* — the POST path commits twice
  before the turn pointer is written, so the lock dies at the first commit.
  Closing it means relaxing one of two pins: claim-the-turn before appending the
  message (visible `activeOperationId` a few ms early, self-healing after 150 s),
  or a single-transaction POST (needs a non-committing seam in
  `operation_service.create`). Third option: leave it.
- **`a2Eligible` vs power.** Add a derived-consistency validator to extraction
  (power > 35 kW ⇒ the flag cannot be true), or drop the extracted flag and
  derive it from power at query time. The observed failure was non-deterministic
  noise, which argues for the cheap validator.
- **Used-price research.** Storage, staleness and the whole UI exist; the
  research command, the estimator wiring and the API field do not. See
  [`../modules/used-prices.md`](../modules/used-prices.md).
- **Preferences never expire.** A live turn was observed applying an
  `a2Eligible` preference recorded in turn 1 after the customer had since
  described themselves as experienced, narrowing touring candidates wrongly.
  Options: let the advisor supersede its own earlier reading, decay
  `exploring`/`soft` rows, or leave it.
- **Structured ingestion warnings.** The admin identity panel parses research
  warnings out of the operation *message* string by prefix. A typed field would
  be cleaner.

## Deliberately not built

- **Document uploads and PDF parsing.** The `upload` source type exists in the
  enum and is unused; PDFs are skipped with a warning. No Docling.
- **In-page link following / crawling.** Ingestion is search-then-fetch.
- **Purpose-built classifieds scrapers.** `robots.txt` on the obvious German
  used-bike sites disallows exactly the price-filter, sort and search-parameter
  paths a sampler would need, so used prices can only ever be a dated snapshot
  of *published* prices with visible sources, never a statistical sample.
- **An alias table.** Type codes resolve through `type_codes`; spellings rely on
  the advisor normalising them plus a punctuation-insensitive resolver. Build
  `motorbikes.aliases` when a transcript shows a real miss.
- **Trim-aware filtering, buildingline as a table, per-trim type codes,
  per-trim provenance, `model_years`.** All consequences of storing trims as
  JSONB deltas; see [`../modules/model-naming.md`](../modules/model-naming.md).
- **Token streaming.** The UI models a seen/typing conversation instead.
- **Rate limiting, audit trail, session-management UI, scheduled ingestion,
  job cancellation, taskiq-admin.**
