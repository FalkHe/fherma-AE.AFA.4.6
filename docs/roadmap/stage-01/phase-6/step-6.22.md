---
phase: 6
step: "6.22"
title: app prices research and app prices delete
summary: A Typer command (not an ingestion stage) researches one approved bike's used prices — own pinned query templates through the existing search provider, robots-gated fetches of provider-returned URLs only, listing source_documents, a fenced json_schema extraction with plausibility clamps, min/max/median/sample_count aggregation and an upsert through used_price_service.
effort: 4
dependencies: ["6.21", "6.17"]
---

# Step 6.22 — `app prices research` and `app prices delete`

**Effort: 4** — a new CLI pair, a new research service composing five landed
pieces, a new extraction module with prompt and clamps, aggregation rules with
edge cases, and a live run against the real web.

Binding contract: `docs/roadmap/stage-01/phase-6/shared-knowledge.md` (**D8** — no
constructed listing URLs ever, provider-returned URLs only, robots gate,
politeness, admin-triggered single-model volume, and the honest "published
pages, not a classifieds sample" consequence; **D9** — the table shape, full
replace, a run that cannot produce a median writes nothing, `sample_count`
NULL = unknown). **Not an ingestion stage**: `_Run.execute`'s milestone
sequence is a pinned contract and its fresh-run delete would couple price
cadence to re-ingestion — this is a Typer command with its own service. Read
`## Landed decisions ### Step 6.13` for `used_price_service`'s landed function
names (pinned intent below — a mismatch is a stop-and-report, not a rename)
and `### Step 6.17` for the provider `templates` seam and `### Step 6.21` for
`RobotsGate`. Agent: **backend-dev**. Zero deviations — a deviation is a
stop-and-report.

**Environment:** stack up; `TAVILY_API_KEY` and `OPENROUTER_API_KEY`
configured. No worker restart (CLI-only paths).

## Outline

- **New** `backend/app/services/used_price_research_service.py`:
  - pinned templates (own constants, `SourceType.LISTING` decides the label,
    the 6.17 seam carries them into the provider unchanged):

    ```python
    PRICE_QUERY_TEMPLATES: tuple[QueryTemplate, ...] = (
        QueryTemplate(SourceType.LISTING, '"{name}" gebraucht kaufen preis'),
        QueryTemplate(SourceType.LISTING, '"{name}" used price for sale'),
        QueryTemplate(SourceType.LISTING, '"{name}" gebrauchtpreis marktwert'),
    )
    ```
  - `async def research(session, motorbike, *, client=None, gate=None) ->
    ResearchResult | ResearchFailure` (typed outcome, the ingestion-adapter
    pattern): search with `templates=PRICE_QUERY_TEMPLATES` using
    `motorbike.query_name`; for each candidate URL (**provider-returned
    only** — never build one), check `RobotsGate.allows(url)` and skip a
    refusal with a warning line; fetch via `fetch.fetch_html`, extract
    markdown via `extract.extract_markdown`, store as a `listing`
    `source_document` through the same `storage.save_raw_document` +
    `document_service.create_document` shape `_store_document` uses
    (announce `document.updated` likewise);
  - one extraction call **per stored page** (provenance is per source);
    aggregate: pool every per-source price → `price_min_eur`/`price_max_eur`
    = pooled extremes (ranges included), `price_median_eur` = median of the
    pooled individual prices with `sample_count` = their count; when **only
    ranges** were found, median = midpoint of the pooled range and
    `sample_count = None` (D8); neither prices nor ranges → **write nothing**
    (D9) and return a failure naming why;
  - upsert through `used_price_service` (pinned intent:
    `upsert_snapshot(session, motorbike_id, *, price_min_eur, price_max_eur,
    price_median_eur, sample_count, as_of, sources)`; `as_of =
    datetime.now(UTC)`; `sources` in the exact D9 JSONB shape:
    `[{"source_document_id", "url", "title", "sample_count", "prices"}]`).
- **New** `backend/app/llm/used_price_extraction.py` +
  `backend/app/llm/prompts/used_price_extraction.md`:
  - `ExtractedUsedPrices(BaseModel)`: `prices: list[int]` (individual EUR
    asking prices; clamps `PRICE_MIN_EUR = 200`, `PRICE_MAX_EUR = 200_000`,
    cap `MAX_PRICES_PER_SOURCE = 40`, out-of-window entries dropped),
    `range_min_eur: int | None`, `range_max_eur: int | None` (same clamps;
    an inverted pair is dropped whole). Same `model_json_schema`
    required-all override and
    `get_chat_model(model).with_structured_output(..., method="json_schema")`
    chain as `extraction.py`; EUR-only rule (a foreign-currency figure is
    dropped, own `_FOREIGN_CURRENCY` regex mirroring `extraction.py`'s).
  - the prompt **fences the fetched page text** exactly as
    `spec_extraction.md` does (`fence()`, `FENCE_START`/`FENCE_END`, the
    untrusted-data paragraph): prices for **this one model** only, asking
    prices not MSRPs, `null`/empty when the page states none.
- **New** `backend/app/cli/prices.py`, registered in `backend/app/cli/main.py`
  (`app.add_typer(prices.app, name="prices")`), CLI async pattern of
  `app.cli.users`:
  - `app prices research <id-or-slug>` — approved rows only (refuse others,
    exit 1); prints one line per URL (`fetched` / `skipped (robots.txt)` /
    `no prices`), then the admin summary: median, min–max, `sample_count`
    (or `unknown`), `as_of`, and one line per source with its URL. A run
    that wrote nothing says so and exits 1.
  - `app prices delete <id-or-slug>` — removes the snapshot via
    `used_price_service` (`delete_snapshot`), prints what was removed, exits
    1 when there is none. The stored `listing` documents stay (provenance).
- Tests: `backend/tests/services/test_used_price_research_service.py`
  (robots refusal skips and warns; only provider URLs fetched; aggregation:
  prices-only, ranges-only → `sample_count is None`, mixed, empty → nothing
  written; second run replaces the row) using mocked provider/transport/
  chain; `backend/tests/llm/test_used_price_extraction.py` (clamps, fences
  present in the rendered prompt); `backend/tests/cli/test_prices.py`
  (approved-only refusal, delete, summary wording).

## Verification

- `make backend-test` and lint green; no new dependency
  (`git diff backend/pyproject.toml` empty).
- Live, real approved row: `app prices research 'honda/cb500f/2013-'`
  fetches only provider URLs (the printed lines are the proof), then
  `docker compose exec postgres psql -U postgres -d app -c "select price_min_eur, price_median_eur, price_max_eur, sample_count, as_of, jsonb_array_length(sources) from motorbike_used_prices;"`
  shows one row, and
  `"select count(*) from source_documents where source_type = 'listing';"`
  is non-zero. Re-run the command: still exactly one snapshot row (full
  replace). `app prices delete 'honda/cb500f/2013-'` removes it; run
  `research` once more so 6.23 has data.
- Not re-proven here: the discard/embedding quarantine (6.21's tests) —
  M4/QA 6.31 re-ingests a priced bike live.

## Risks / notes

- The researched figure is what published pages say — 6.29 documents that
  honestly; this step's summary output must not claim "market average".
- The provider's result cap is `INGESTION_MAX_WEB_DOCUMENTS` (6) via the
  landed limit — acceptable volume per D8 item 4; do not raise it here.
- 6.22 formally depends only on 6.21, but uses 6.17's `templates` seam — the
  backend track is sequential, so it is landed; if it is somehow absent,
  stop and report rather than re-implementing a query path.
- `used_price_service` function names: if 6.13 landed different ones, use
  the landed names and record the mapping — changing 6.13's module is not
  this step's right.
- Append (`### Step 6.22`) to `shared-knowledge.md`: the template strings,
  the aggregation rules (ranges-only ⇒ `sample_count NULL`), and the CLI
  summary line QA 6.31 greps for.
