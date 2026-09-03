---
phase: 6
step: "6.21"
title: listing documents quarantined and the robots.txt gate
summary: SourceType.LISTING is excluded from _discard_previous_run and from the chunking/embedding path (with a test proving ingestion is otherwise untouched), and a stdlib urllib.robotparser gate lands for the price fetch path, reusing PolitenessGate and USER_AGENT. Zero new dependencies.
effort: 3
dependencies: ["6.13"]
---

# Step 6.21 — `listing` documents quarantined and the robots.txt gate

**Effort: 3** — four narrow carve-outs in landed paths plus one small
self-contained module, all provable by unit tests; nothing here talks to the
live web yet (6.22 wires the gate).

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (**D12** — the
**four** carve-outs, exactly, two of which were added when this step was
adjudicated on 2026-08-31; **D8** items 2–3 and 5 — stdlib parser, existing
`PolitenessGate` + `USER_AGENT`, price path only; hard rule — **zero new
dependencies**). The `listing` enum value exists since 6.13. Agent:
**backend-dev**. Zero deviations — a deviation is a stop-and-report.

**Environment:** stack can stay as it is (unit-test step); `make backend-test`
runs in the one-off CLI container. No worker restart required by the contract
for this step; the carve-outs first matter once 6.22 stores `listing` rows.

## Outline

- `backend/app/services/document_service.py` — additive keyword on
  `list_for_motorbike(session, motorbike_id, *, exclude_source_types:
  Sequence[SourceType] = ())`; default behaviour byte-identical.
- `backend/app/services/ingestion/service.py` — `_discard_previous_run`
  (D12): list documents with
  `exclude_source_types=(SourceType.LISTING,)` (so a listing document's file
  is never unlinked) **and** add
  `SourceDocument.source_type != SourceType.LISTING` to the delete
  statement. A re-ingestion must not wipe price provenance. Nothing else in
  `_Run` moves — the milestone sequence is a pinned contract.
- `backend/app/services/embedding_service.py` — `rebuild_motorbike` lists
  documents with the same exclusion, so **no chunk and no embedding is ever
  built from a `listing` page** (dated asking prices must never enter the RAG
  knowledge base). This is the chunking entry point; no second path exists.
- `backend/app/services/spec_extraction_service.py` — `assemble_documents`
  lists with the same exclusion (**D12**, third carve-out). A used listing in
  the extraction prompt would feed asking prices into `msrp_eur`, which is a
  **new-bike** field (D9): an ad is not a specification source. Test: an
  extraction over a document set containing a `listing` row builds a prompt
  that does not contain its text.
- the customer-facing catalogue-detail `sources[]` projection (**D12**, fourth
  carve-out) — find the projection that serves
  `GET /api/catalogue-models/{id}` and apply the same exclusion, so a
  classifieds link is never presented as provenance for a specification. Test:
  a bike with a `listing` document serves a detail payload whose `sources[]`
  does not mention it. **Admin** surfaces still show `listing` documents —
  that is where an admin audits what the price research fetched, so do not
  exclude them from the products/documents resources.
- **New** `backend/app/services/ingestion/robots.py` — the gate 6.22 calls
  on the price fetch path only:
  - `class RobotsGate:` `__init__(self, *, client: httpx2.AsyncClient, gate:
    fetch.PolitenessGate | None = None)`; one method
    `async def allows(self, url: str) -> bool`.
  - Per host (lower-cased, port dropped — reuse the `fetch._host` rule),
    fetch `{scheme}://{host}/robots.txt` **once** through the given client
    (which carries the pinned `USER_AGENT`), after `gate.wait(host)`; cache
    the resulting `urllib.robotparser.RobotFileParser` (fed via
    `parser.parse(lines)`) for the object's lifetime.
  - Pinned outcome table (documented in the docstring): HTTP 2xx → parse and
    answer `parser.can_fetch(USER_AGENT, url)`; 401/403 → disallow the host
    (the stdlib convention); any other 4xx → allow (no robots policy);
    5xx / timeout / network error → **disallow** the host (conservative) —
    the caller prints the visible warning either way (D8 item 2). The module
    itself only returns booleans and logs one `logger.warning` per refused
    host.
  - stdlib only — importing anything new into `pyproject.toml` is a
    stop-and-report.
- Tests:
  - extend the `_discard_previous_run` coverage in
    `backend/tests/services/ingestion/test_service.py`: seed one `listing`
    and one `wikipedia` document (rows + fake files); after the discard the
    `listing` row **and file** survive, the others are gone, and — the
    "otherwise untouched" proof — a bike with no `listing` documents discards
    exactly what it discarded before this step (assert on the same fixtures
    the existing test uses).
  - `backend/tests/services/test_embedding_service.py`: a `listing` document
    produces no chunks in `rebuild_motorbike`, while its sibling documents
    chunk exactly as before.
  - **New** `backend/tests/services/ingestion/test_robots.py`: mocked
    transport per outcome-table row (allow, disallow path, 403, 404, 500,
    timeout), the per-host cache (one robots.txt fetch for two URLs), and
    the politeness gate awaited (inject the fake-clock gate the fetch tests
    use).

## Verification

- `make backend-test` and lint green — the whole step is unit-proven; there
  is deliberately **no live smoke** here (nothing writes `listing` documents
  until 6.22, whose verification covers the gate against the real web).
- `uv run ruff check .` clean; confirm `pyproject.toml` has no new entry
  (`git diff backend/pyproject.toml` is empty).

## Risks / notes

- **Resolved (2026-08-31): both gaps are now in scope.** The step author
  found that D12's original two carve-outs leaked — `assemble_documents` would
  feed listing pages into the next re-extraction's prompt, and the customer
  catalogue detail's `sources[]` projection would show listing links as
  provenance. D12 now names **four** carve-outs and this step implements all
  four; the effort moved 2 → 3. Admin surfaces deliberately keep showing
  `listing` documents — that is where the price research is audited.
- The `exclude_source_types` default of `()` keeps every other caller
  byte-identical — that is the "ingestion otherwise untouched" claim; do not
  flip any other call site.
- 6.22 depends on `RobotsGate.allows` and on the survive-discard behaviour;
  M4's demo re-ingests a priced bike to prove it live.
- Append (`### Step 6.21`) to `shared-knowledge.md`: the `RobotsGate` API,
  its outcome table, and the `exclude_source_types` keyword.
