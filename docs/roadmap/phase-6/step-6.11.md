---
phase: 6
step: "6.11"
title: "naming_service: name parts and the escalation algorithm"
summary: The one rendering module — NameLevel, NameParts, load_name_parts, render_name, render_names, render_buildingline — implementing the three-level escalation with the query_name fallback, wired nowhere; plus `app catalogue render-name` for debugging and table-driven tests over the doc's own examples.
effort: 3
dependencies: ["6.10"]
---

# Step 6.11 — `naming_service`: name parts and the escalation algorithm

**Effort: 3** — one new pure module with a precise algorithm, a batched read
helper, a debug CLI command and a table-driven test file; no existing code
changes, which is what keeps it one session.

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (**D5** — this
module is the only place parts become a string; `render_name` never queries;
the fallback is load-bearing) and `docs/roadmap/model-naming-data-model.md`
§4.4 + §5 (signatures and the six-step algorithm — implement them **exactly**
as written there, including the per-caller `context`/`min_level` table that
6.19/6.20 will consume). Naming semantics: `docs/model-naming.md` ("Rendering
rule", "Year range instead of a single year", "Examples"). **Wired nowhere** —
no tool, endpoint or service starts calling this; wiring is 6.19/6.20. Agent:
**backend-dev**. Zero deviations — a deviation is a stop-and-report.

**Environment:** stack up for the CLI check; the dev DB rows all have
`model_name IS NULL` today, so the CLI will demonstrate the fallback — use
`app catalogue set-identity` only after 6.12; for this step the escalation is
proven by tests, the CLI by its exit paths.

## Outline

- **New** `backend/app/services/naming_service.py`, exactly the §5 surface:
  - `class NameLevel(IntEnum)`: `BUILDINGLINE = 0`, `MODEL = 1`, `YEAR_RANGE = 2`;
  - `@dataclass(frozen=True, slots=True) class NameParts`: `motorbike_id`,
    `manufacturer`, `buildingline`, `model_name`, `year_from`, `year_to`,
    `query_name` (types per §5);
  - `async def load_name_parts(session, motorbike_ids: Sequence[str]) -> dict[str, NameParts]` —
    two selects, no ORM relationships: the motorbike columns by id, then the
    referenced manufacturers' names by collected `manufacturer_id`; unknown ids
    are simply absent;
  - `def render_name(parts, *, context: Sequence[NameParts] = (), min_level: NameLevel = NameLevel.MODEL) -> str` —
    the six algorithm steps verbatim: `model_name is None` → `query_name`
    verbatim (**never** an error — the load-bearing fallback); start at
    `max(MODEL, min_level)`; ambiguity = another `context` member with a
    different `motorbike_id` rendering the same string at the current level;
    escalate to the year range against the colliding subset only; year range
    renders `(2019–2023)` (en dash), `(from 2023)` when `year_to is None`,
    skipped entirely when `year_from is None`; a collision surviving the year
    range appends the last 6 characters of the id and `logger.warning`s;
  - `def render_names(parts: Sequence[NameParts], *, min_level=NameLevel.MODEL) -> dict[str, str]` —
    each member rendered with the others as context;
  - `def render_buildingline(parts: NameParts) -> str | None` — level 0,
    headings/facets only.
- `backend/app/cli/catalogue.py`: new command `render-name`
  (`app catalogue render-name <motorbike-id> --context <id> --context <id>`):
  `load_name_parts` over the id set, echoes `render_name` at `MODEL` and at
  `YEAR_RANGE` min-level (two labelled lines); unknown id → `_fail`. Same
  `asyncio.run` pattern as `set-manufacturer`.
- Tests: **new** `backend/tests/services/test_naming_service.py`, table-driven
  over the doc's own rows — the `docs/model-naming.md` "Examples" table
  (e.g. `Kawasaki Z900 (2020–2024)`, `Ducati Multistrada V4 S (2021–2024)`)
  and its year-range table (`BMW R 1250 GS (2019–2023)`); plus: fallback
  (`model_name=None` → `query_name` verbatim), no-context render at each
  `min_level`, escalation only for the colliding subset (three rows, two
  colliding: the third stays short), open range, missing `year_from`, the
  id-suffix last resort asserted with `caplog` catching the warning, and
  `render_names` mutual-context behaviour. CLI test added to
  `backend/tests/cli/test_catalogue.py` (stubbed session, both exit paths).

## Verification

- `make backend-test` + `make lint` green; the new test file is the
  algorithm's proof — every table row cites which doc example it encodes.
- Live CLI smoke: `docker compose run --rm app-cli app catalogue render-name <id>`
  with any dev-DB id prints that row's `query_name` (the fallback, since no
  identity exists yet), and an invented id exits non-zero. The escalated-name
  live demo belongs to the M1 milestone check, after 6.12's `set-identity`.
- Nothing else to verify: no wire surface, no schema, no migration in this step.

## Risks / notes

- 6.12 imports nothing from here (slug is computed from columns, not rendered
  names) but 6.19 and 6.20 consume every symbol above plus the §5 caller
  table — treat all names and defaults as frozen once landed.
- Do not add caching, DB queries inside `render_name`, or a database-wide
  ambiguity check — D5 explicitly forbids all three.
- Append (`### Step 6.11`) to `shared-knowledge.md`: the exact rendered
  formats (`(2019–2023)`, `(from 2023)`, id-suffix form) so 6.19/6.20/QA
  assert against one spelling.
