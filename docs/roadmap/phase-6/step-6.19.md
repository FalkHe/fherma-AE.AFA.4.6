---
phase: 6
step: "6.19"
title: Resolution and rendering wired in
summary: resolve_name gains the type-code leg and a two-column substring, BrowseSort.NAME becomes the composite sort, the read models carry NameParts, and the five name-carrying tools plus both JSON:API resources render names in context per the pinned per-caller table — wire keys unchanged, 6.14's fences preserved.
effort: 4
dependencies: ["6.11", "6.14", "6.18"]
---

# Step 6.19 — Resolution and rendering wired in

**Effort: 4** — one service rewrite with a new resolver leg and a composite
sort, two read models widened, five tools and two endpoint modules switched to
rendered names, all against pinned wire shapes; broad but mechanical, and
6.11's `naming_service` does the actual rendering.

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (**D5** — the
per-caller `context`/`min_level` table in `docs/roadmap/model-naming-data-model.md`
§5 is binding; **D6** — `suggestion->'type_codes'` is a retrieval hint only;
**D7** — **6.14's fences must survive**: `retrieve_bike_knowledge`'s
`_model_view` sentinels over snippet text, `sourceTitle` and `headingPath` are
untouched by this step, and identity strings are deliberately *not* fenced;
pinned wire shapes stay additive — every tool-result key and API attribute
keeps its key and type, only the `name` **values** improve). Detail:
data-model §4.3, §5, §6. Read `## Landed decisions ### Step 6.11` for the
exact `naming_service` API. Agent: **backend-dev**. Zero deviations — a
deviation is a stop-and-report.

**Environment:** stack up; 6.18 landed (canonical slugs on the approved
rows). **Restart `app-worker` after landing** — tools run in the worker.

## Outline

- `backend/app/services/catalogue_search_service.py` (the **only** step that
  touches this file):
  - `resolve_name` order becomes **exact slug → type code → substring**. The
    type-code leg upper-cases/trims the input and matches approved rows by
    JSONB containment (`@>`) on `type_codes` **or**, as a hint only, on
    `suggestion->'type_codes'`; exactly one matching row → return it; several
    → fall through (never guess); none → fall through. The substring leg now
    matches `Motorbike.query_name` **or** `Motorbike.model_name` (`ILIKE`,
    same escaping), ordered by
    `least(char_length(query_name), coalesce(char_length(model_name), 32767))`
    then `query_name`, then `id` — shortest match still wins,
    deterministically. "Approved only" and "`None`, never an exception"
    unchanged.
  - `BrowseSort.NAME` becomes the composite
    `(Manufacturer.name ASC NULLS LAST, Motorbike.model_name ASC NULLS LAST,
    Motorbike.year_from ASC NULLS LAST, Motorbike.id ASC)` via an outer join
    to `manufacturers` in both browse statements (the count is unaffected —
    the join cannot multiply rows). `NAME_DESC` mirrors the first two columns
    descending, id still ascending. Wire values `name`/`-name` unchanged.
  - `VerifiedSpecs` and `BrowseRow` gain `parts: naming_service.NameParts`
    (loaded in the same statements — no extra query per row); their `name`
    attribute survives as `render_name(parts)` for the no-context caller.
- Callers render per the binding §5 table:
  - `backend/app/llm/agents/tools/catalogue_search.py` — `context` = the
    returned rows, `min_level = MODEL`.
  - `backend/app/llm/agents/tools/spec_comparison.py` — the compared rows,
    `YEAR_RANGE`.
  - `backend/app/services/fit_check_service.py` and
    `backend/app/services/cost_estimator_service.py` — `name =
    render_name(entry.parts, min_level=NameLevel.YEAR_RANGE)` (one-line each);
    their tools (`licence_fit_check.py`, `cost_estimator.py`) pass it through.
  - `backend/app/llm/agents/tools/present_recommendations.py` — the presented
    batch as context, `YEAR_RANGE` (via `naming_service.load_name_parts` for
    the batch).
  - `flag_unknown_bike.py` keeps writing `query_name` (unchanged);
    `retrieve_bike_knowledge.py` and `record_preference.py` untouched.
- `backend/app/api/endpoints/products.py` — `name` = rendered at `MODEL`,
  context `()` (the additive `queryName` attribute is 6.20's, not this
  step's). `backend/app/api/endpoints/catalogue_models.py` — list: context =
  the page, `MODEL`; detail: `()`, `YEAR_RANGE`. Attribute keys unchanged.
- Tests: resolver leg order (code hit, ambiguous code falls through, hint via
  `suggestion`), two-column substring, composite sort order, and one
  rendered-shape test per changed tool asserting the **keys** are unchanged
  and the name escalates only under a colliding context. Existing 6.14
  fencing tests stay green untouched — that is the fence-survival proof.

## Verification

- `make backend-test` and lint green; `docker compose restart app-worker`.
- Live, real rows: `app tools run cost_estimator '{"motorbikeName":"WVB9"}'`
  resolves through the type-code hint/column to the Suzuki GSR600 and its
  result `name` reads `Suzuki GSR600 (2006–2011)` (YEAR_RANGE floor).
  `app tools run catalogue_search '{}'` shows year ranges **only** where two
  result rows would otherwise render the same string.
- `curl -s 'localhost:8000/api/catalogue-models?sort=name' | jq '.data[].attributes.name'`
  (with the landed auth cookie pattern) is ordered brand → model → year, and
  the response carries exactly the pre-step attribute keys.
- Do **not** re-prove approval guards (6.12/6.18) or run adversarial fencing
  input — M2 proved the fences, QA 6.30 owns behavioural acceptance.

## Risks / notes

- `resolve_name`'s type-code leg reads a *claim* (`suggestion->'type_codes'`)
  to find a row — D6 explicitly allows that; it must never surface the claim
  in any output.
- The GSR600 code smoke depends on `WVB9` being present either in the
  approved row's `type_codes` (if an admin set it in 6.18's `set-identity`)
  or in a `suggestion` hint on an approved row; if neither holds in the dev
  DB, set it first with `app catalogue set-identity` — that is data setup
  through a landed path, not scope creep.
- 6.20 serialises what this step computes; 6.23 adds to `cost_estimator`'s
  result — neither may drop the rendered `name` or any 6.14 sentinel.
- Append (`### Step 6.19`) to `shared-knowledge.md`: the final resolver leg
  order, the composite sort tuple, and where `parts` lives on the read
  models.
