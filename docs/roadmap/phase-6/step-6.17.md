---
phase: 6
step: "6.17"
title: Suggested links and type codes as research input
summary: suggestion.links become SearchCandidates fetched before the generic web search, claimed type_codes become one extra pinned search query, and a claim the sources contradict is recorded through the existing _Run._warn — no new column, claim and finding both stand.
effort: 3
dependencies: ["6.15"]
---

# Step 6.17 — Suggested links and type codes as research input

**Effort: 3** — three surgical changes inside a pinned orchestration
(`_Run.execute`'s milestone sequence must not move), one additive provider
seam, tests, and a live ingestion smoke.

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (**D6** — the
claim is a research *input hint*, never catalogue data; **D13** — warnings
ride `_Run._warn`, no new column, claim never overwrites finding nor vice
versa). The suggestion JSON shape is documented in
`backend/app/cli/suggestions.py` (`links`, `type_codes`, `year_from`,
`year_to`). Agent: **backend-dev**. Zero deviations — a deviation is a
stop-and-report.

**Environment:** stack up; keys configured. **Restart `app-worker` after
landing.** 6.15 has landed (`_assign_identity` exists, extraction returns
identity fields).

## Outline

- `backend/app/services/ingestion/search.py`:
  - additive keyword on **both** providers and the `SearchProvider` protocol:
    `search(name, *, client=None, gate=None, templates: tuple[QueryTemplate, ...] = QUERY_TEMPLATES)`
    — default behaviour byte-identical; the loop iterates `templates` instead
    of the module constant. (6.22 reuses this seam for its price templates —
    do not special-case it for type codes.)
  - public `def strip_utm_source(url: str) -> str` delegating to the existing
    `_without_utm_source` (12 of the imported backlog links carry
    `?utm_source=chatgpt.com`; the function already strips exactly that
    parameter and keeps every other one).
- `backend/app/services/ingestion/service.py`:
  - module constants: `MAX_SUGGESTED_LINKS = 3`,
    `SUGGESTED_LINK_SOURCE_TYPE = SourceType.TECHNICAL` (a claimed reference
    is technical input — never `WIKIPEDIA`, so the customer-facing `_article`
    pick and the extraction trust order stay owned by the vetted Wikipedia
    stage), `MAX_TYPE_CODE_TERMS = 2`,
    `CLAIM_YEAR_WARNING = "Suggestion contradicted: claimed years {claimed}, sources say {found}."`,
    `CLAIM_CODE_WARNING = "Suggestion contradicted: claimed type codes {claimed}, sources printed {found}."`.
  - `_search_stage`: read `self.motorbike.suggestion` (may be `None`). Build
    suggested candidates **first**: for each of the first
    `MAX_SUGGESTED_LINKS` entries of `suggestion["links"]`, a
    `SearchCandidate(url=strip_utm_source(link), title=link,
    source_type=SUGGESTED_LINK_SOURCE_TYPE)`. The stored claim JSON is never
    modified (D6) — only the fetch candidate is cleaned. When
    `suggestion["type_codes"]` is non-empty, extend the provider call's
    `templates` with **one** extra query template:
    `QueryTemplate(SourceType.TECHNICAL, '"{name}" ' + " ".join(codes[:MAX_TYPE_CODE_TERMS]) + ' motorcycle specifications')`.
    Return suggested candidates + provider candidates, deduplicated by URL
    (suggested first, so a provider duplicate is dropped, not the claim's
    link). The `SEARCH_MILESTONE` progress/message and the warning flow are
    untouched — a failed suggested-link fetch is the same `_warn` any
    candidate gets in `_fetch_candidate`.
  - `_extraction_stage`: on a successful `ExtractionResult`, first feed each
    of 6.15's `outcome.identity_warnings` to `self._warn(...)` (the dropped
    type-code/variant entries — D1's warning-on-the-run rule, deferred to
    this step because this file's edits are pinned to 6.17/6.21). Then
    compare claim against finding and `self._warn(...)` on contradiction —
    **years**: warn
    (pinned `CLAIM_YEAR_WARNING`) when the claim has `year_from` and the
    extraction produced `year_from`/`year_to` that differ from the claimed
    pair; **codes**: warn (pinned `CLAIM_CODE_WARNING`) when the extraction
    produced a non-empty `type_codes` list sharing **no** code with the
    claimed list (a found subset is not a contradiction — a source simply did
    not print every code). Neither value overwrites the other: the typed
    columns hold the finding (6.15), `suggestion` holds the claim, the
    reviewer decides (D13).
- Tests — extend `backend/tests/services/ingestion/test_service.py` (or the
  file that owns `_Run` today): suggested links fetched before provider
  candidates and deduped; utm parameter stripped on the candidate but intact
  in `motorbike.suggestion`; type-code template passed to the provider; both
  contradiction warnings fire (and do not fire on a matching claim / a found
  subset); a row without `suggestion` behaves byte-identically to today.
  Extend the search tests for the `templates` keyword default.

## Verification

- `make backend-test` and lint green; `docker compose restart app-worker`.
- Live smoke — real backlog row **BMW F 750 GS** (claim `[K80]`, 2018–2023,
  and a `?utm_source=chatgpt.com` Wikipedia link): `app ingest run
  "BMW F 750 GS"`, wait for completion, then
  `docker compose exec postgres psql -U postgres -d app -c "select source_type, source_url from source_documents sd join motorbikes mb on mb.id = sd.motorbike_id where mb.query_name = 'BMW F 750 GS';"`
  shows a `technical` document whose URL is the claimed Wikipedia page
  **without** the `utm_source` parameter. If the sources dated the model
  beyond 2023, the operation message carries the pinned
  `Suggestion contradicted: claimed years …` text
  (`docker compose exec postgres psql -U postgres -d app -c "select message from operations order by created_at desc limit 1;"`);
  the warning path itself is proven by the unit tests either way — do not
  chase a live contradiction.

## Risks / notes

- The `templates` keyword is the one seam 6.22 builds on; renaming or
  removing it later is a cross-step break — record it in Landed decisions.
- `_wikipedia_stage`/`_search_stage` read the motorbike's name field renamed
  by 6.9 (`query_name`); this step touches those lines — keep the 6.9 rename,
  do not reintroduce `.name`.
- `MAX_SUGGESTED_LINKS` candidates are *additional* to the provider cap
  (`INGESTION_MAX_WEB_DOCUMENTS = 6`); in the backlog corpus a row carries at
  most 1 link, so the fetch band arithmetic (`_fetch_progress`) needs no
  change — it already divides by the actual total.
- Append (`### Step 6.17`) to `shared-knowledge.md`: the `templates` seam
  signature, `SUGGESTED_LINK_SOURCE_TYPE`, and the two pinned warning
  strings (the review UI 6.27 and QA 6.30 grep for them).
