# Model naming — target data model and migration path

Architecture proposal, 2026-08-30. **Owner decisions applied 2026-08-31** (§0).
Turns the binding domain knowledge in [`../../modules/model-naming.md`](../../modules/model-naming.md)
into a schema, a rendering contract and a sliced migration path from
`phase-5-done` (migration head `fb2747f937c4`).

Nothing here is implemented. It is a decision document: the owner has decided
the four load-bearing questions (§0); the rest is sliced into
`docs/roadmap/stage-01/phase-6/` in the usual shape (shared-knowledge, step files,
ui-spec).

Binding context: [`../../general/architecture.md`](../../general/architecture.md),
[`../../general/backend-stack.md`](../../general/backend-stack.md), the Phase-2/2b conventions
(ULID PKs, **no ORM relationships**, services own transactions, get-or-create
by slug).

---

## 0. Owner decisions (2026-08-31)

| # | Decision | Effect |
|---|---|---|
| D1 | **A `motorbikes` row is a generation**, not a marketing model. | §1 stands as written; the frozen `motorbike_specs` set does not move. |
| D2 | **No `variant_name` column, and no row per trim.** Only the base variant is a row. Every trim lives in the `variants` JSONB — its name, the specifications that *differ from or are added to* the base, and a free-text `description` for anything not a specification (gear, colours, packages). | §2.2 loses `variant_name`; §2.5 rewritten; the name escalation loses its variant level (§5); identity and slug lose the variant segment (§3). |
| D3 | **No `aliases` table for now.** Alias strings are metadata text, added only if the need is proven. The advisor LLM is expected to normalise "R1300GS" → "R 1300 GS" before it calls a tool. | §2.3 rewritten as a deferred, column-shaped fallback; the alias step drops out of `resolve_name`, the alias service, the seed file and two migration steps. |
| D4 | **Trim-aware filtering is a known gap, not this change.** A hard `fuel_capacity ≥ 15 l` filter excludes a base row whose Adventure trim carries 20 l. Recorded under "Future upgrades" in [`../roadmap.md`](../roadmap.md); not handled now. | §9. |
| D5 | **A generation may carry several type codes**, held as a list. Codes are *retrieval* metadata first: ingestion notes every code the sources show, and they become search terms and a resolver leg. They are never identity and never customer-visible. | §2.2 `type_code` → `type_codes` (array); §3 the slug's generation segment is **always the year range**; §4.2 approval requires a year range; §4.3 gains a type-code resolution leg; §5 loses its type-code render level. |
| D6 | **No `buildinglines` table.** The model family is a nullable text column on `motorbikes`; grouping is `GROUP BY` on that column. | §2.1 rewritten; `buildingline_id` → `buildingline`; no `buildingline_service`, one normalisation helper instead; one fewer table in the first migration. |

Everything below is written against these decisions.

---

## 1. The one decision everything else follows from

The domain doc puts five levels under a manufacturer (buildingline → model →
generation → variant → model year) and then says two things that pull in
opposite directions:

- *"Displacement, power, licence class and emission standard belong on
  `Generation`/`Variant`, never on `Model`."*
- *"A model is identified by manufacturer, buildingline, variant and year
  range"* — the **search unit** is the marketing model.

We already have exactly one table that owns a specification row, a document
set, a chunk set and an image set: `motorbikes`. The whole blast radius of
this change is decided by what one `motorbikes` row *means*.

**Decision (D1): a `motorbikes` row is a generation, not a marketing model.**
One row per (manufacturer, model name, year range / type code). "BMW R 1250 GS
(2019–2023)" and "BMW R 1300 GS (from 2023)" are two rows, as they already are
in the seed list today. Trims never split a row (D2).

This is the simpler of the two viable designs: the alternative — `motorbikes`
stays the marketing model and a new `generations` table owns the specs —
would re-parent `motorbike_specs`, `source_documents`, `chunks` and
`motorbike_images`, and rewrite all 8 tools, both JSON:API resources and the
frozen `SpecFilters` SQL, for no gain the customer can see.

**Consequence, stated loudly: the frozen `motorbike_specs` column set does
not move and is not re-parented.** It stays one row per (motorbike, kind),
and that motorbike is now, by definition, the level the domain doc says specs
belong to. Those specs describe **the base trim**. Phase-3's tools keep
filtering on exactly the columns they filter on today — with the known blind
spot D4 records.

The marketing model still exists as a first-class concept; it is just not a
row. It is `(manufacturer_id, model_name)`, materialised as a grouping in
queries, exactly like `year_from`/`year_to` are the year range without a
`model_years` table.

---

## 2. Target schema

### 2.1 Buildingline — a text column, not a table (D6)

The model family: BMW GS, Honda CBR, Yamaha MT, Honda Africa Twin. Its only
jobs are grouping (catalogue headings, a browse facet) and the level-0 name the
domain doc reserves for category pages. With D3 removing the alias table, no
foreign key ever points at a family, so a table would buy referential integrity
nobody consumes.

```
motorbikes.buildingline  String(64) NULL
```

Nullable forever: not every model belongs to a family anyone names. Grouping is
`GROUP BY manufacturer_id, buildingline`; a facet is
`SELECT DISTINCT buildingline … WHERE buildingline IS NOT NULL`.

**The drift guard**, since the reason to prefer a table was that free text
drifts (`GS` / `gs` / `G S`, the way `Kawasaki` / `Kawasaki Motors` drifts
today):

- one helper, `normalise_buildingline(session, manufacturer_id, name)` (§4.1):
  trim, collapse inner whitespace, then **case-insensitively match the
  manufacturer's existing distinct values and reuse the stored casing**. First
  writer wins the spelling, every later writer joins it — the same effect
  `get_or_create` had, without a row;
- the review form offers `Autocomplete freeSolo` over that manufacturer's
  distinct values (display spec §6.2), which is what stops an admin inventing a
  third spelling;
- extraction goes through the helper, never writes the column directly.

If a facet UI or per-family content (a logo, a description, an alias target)
ever ships, promoting the column to a table is a mechanical migration —
distinct values become rows, the text column becomes an FK. Recorded under
"Future upgrades"; nothing in §3–§5 assumes either shape.

### 2.2 `motorbikes` (changed)

| Column | Change | Why |
|---|---|---|
| `name` → `query_name` | **rename**, `String(160) NOT NULL` | It is not a name, it is the phrase an admin (or `flag_unknown_bike`) typed. It seeds the ingestion query, it is a matching surface, and it is the fallback when a row has no structured identity yet. It is **never rendered as the model's name** once the identity is filled. |
| `slug` | unchanged type, new derivation (§3) | still the unique identity |
| `manufacturer_id` | unchanged (`NULL`able) | required only from `approved` (§4.2) |
| `buildingline` | **new** `String(64) NULL`, indexed with `manufacturer_id` | the model family, free text through one normalisation helper (§2.1). Nullable forever; never part of the identity |
| `model_name` | unchanged (`String(128) NULL`) — finally written | the marketing model: "R 1300 GS", "MT-07", "CBR1000RR-R Fireblade" |
| `year_from`, `year_to` | unchanged (`SmallInteger NULL`) — finally written | `year_to IS NULL` = still built ("from 2023") |
| `type_codes` | **new** `JSONB NOT NULL DEFAULT '[]'::jsonb` | every manufacturer code this generation is known by — `["K81"]`, `["SC82"]`, `["FLSTF", "FLFB", "FLFBS"]` (§2.3). Internal: a retrieval and resolution key, **never** rendered to a customer and never part of the identity |
| `variants` | **new** `JSONB NOT NULL DEFAULT '[]'::jsonb` | every trim of this generation except the base, with its spec deltas (§2.5) |
| `status` | unchanged | |

**No `type_code` singular column** (D5): a generation is routinely known by
more than one code — Harley lists a model code per trim and per generation on
one machine, and Yamaha's MT-07 carries `RM48`–`RM51` for one model year.
Forcing one code per row would either drop information or split rows that are
one machine.

**No `variant_name` column** (D2). The row *is* the base trim; a trim is never
a row. Empty `variants` means "no trims worth recording", not "this is the
base of something else".

No new unique constraint: `slug` remains the single identity, and it is
derived deterministically from the parts (§3), so a duplicate identity is a
duplicate slug and raises the existing `DuplicateModelError`.

### 2.3 Aliases — deferred (D3)

The domain doc calls an alias table mandatory ("R1300GS" vs "R 1300 GS",
Harley's FLFBS, "my 1250", the type codes a workshop question uses). The owner
has deferred it: the advisor is an LLM that normalises spelling and spacing on
its own before it calls `catalogue_search` or `spec_comparison`, and today's
resolver already absorbs case and punctuation through `slugify`.

**What ships instead, now:** `resolve_name` grows one cheap leg — **exact
slug → type code → substring** — and the substring leg is widened to search
`query_name` *and* `model_name` (§4.3). Because `type_codes` is a list (D5),
that one leg covers every manufacturer code the sources named, including the
Harley model codes the domain doc calls out: a row for the Fat Boy carries
`["FLSTF", "FLFB", "FLFBS"]` and all three resolve to it.

**What the type-code leg does not cover**, and what therefore remains the
LLM's job: *spellings* of the marketing name — `R1300GS` for `R 1300 GS`,
`Multistrada V4S`, `my 1250`. A code is a token the sources publish; a
spelling is a customer's typing. The first is now data, the second is
normalisation the advisor does before it calls a tool.

**The fallback, if and only if the need is proven** — a metadata column, not a
table:

```
motorbikes.aliases  JSONB NOT NULL DEFAULT '[]'::jsonb   -- ["R1300GS", "FLFBS", "R 1300 GS Adventure"]
```

Plain strings, ≤ 20 entries, ≤ 160 chars each; written by extraction and by
the review form; matched by normalising both sides and comparing — a GIN index
only if the row count ever makes that matter. No FKs, no `kind`/`source`
enums, no ambiguity resolution: a string that matches two rows is two
candidates, and the advisor asks back in prose, which is what it would have
done anyway.

**Trigger to build it** (any one is enough, and it is a one-step change):

- QA or the transcript log shows the advisor failing to resolve a spelling
  that neither the type-code leg nor the substring leg can reach;
- marque abbreviations ("Beemer", "Duc") appear in real questions.

Until then this stays a documented gap, not a table.

### 2.4 `type_codes` — shape and semantics (D5)

```json
["FLSTF", "FLFB", "FLFBS"]
```

Rules:

- an array of plain strings, **order is not meaningful** and nothing may
  depend on it (there is no "primary" code);
- normalised on write: trimmed, upper-cased, deduplicated; shape validated
  against `^[A-Z0-9][A-Z0-9\-/ ]{1,31}$`, entries failing it are dropped with
  a warning on the run, never failing it;
- at most 8 entries;
- **not unique across rows.** The same code may legitimately sit on two rows
  (a code reused across a model split, or an ambiguous code an admin has not
  yet sorted out). A lookup therefore returns 0..n candidates — one is a hit,
  several is a question the advisor asks in prose, none falls through to the
  substring leg. Same policy the deferred alias table would have had;
- **never part of the identity or the slug** (§3), so adding or correcting a
  code is a harmless edit that cannot collide with another row;
- **never rendered to a customer** — no name level, no card, no `alt`, no page
  title. Admin surfaces show them as chips (display spec §6.1).

**Who writes them.** Ingestion, from what the sources actually print — the
prompt rule stays *never invent a code*, and a list makes that rule more
important, not less. The suggestion import already parses the bracket in
`backend/resources/bike-list.txt` into `suggestion["type_codes"]`
(`backend/app/cli/suggestions.py`), so those codes exist per row today as an
unverified **claim**; the resolver may read them (they are a retrieval hint,
not customer-visible data), but only ingestion writes the typed column, and
only for codes a source showed.

**The one risk this accepts.** A row carrying `FLSTF` *and* `FLFB` may be two
generations that nobody split — D1 says those are two rows. Nothing in the
schema can catch that; the year range is the guard, and the reviewer splits the
row when the sources show a new frame or engine. Worth a line in the review
screen's help text, not a constraint.

### 2.5 `variants` JSONB — shape (D2)

The row is the base. Each entry is one trim, carrying **only what differs from
the base or is added to it**:

```json
[
  {
    "slug": "adventure",
    "name": "Adventure",
    "specs": {"fuel_capacity_l": 30, "wet_weight_kg": 268, "seat_height_mm": 890},
    "description": "Tubeless cross-spoked wheels, larger screen, engine bars."
  },
  {
    "slug": "triple-black",
    "name": "Triple Black",
    "description": "Colour and equipment package, mechanically identical to the base."
  }
]
```

Rules:

- an array, order = display order; **the base is never an entry** — it is the
  row itself and the `motorbike_specs` row;
- `slug` unique within the row and equal to `slugify(name)`; `name` ≤ 64 chars;
- `specs` is optional. Keys are restricted to the frozen spec column names
  (the same set `motorbike_specs` carries, plus `extra` for the free-form
  bag), values keep the column's type. **A key present means "this trim's
  value", a key absent means "same as the base"** — a delta, never a full
  spec set;
- `description` (renamed from the earlier draft's `note`) ≤ 400 chars, for
  everything that is not a specification: gear, colours, packages, wheels,
  electronics;
- at most 20 entries.

Validated by a Pydantic model at the API boundary and in the extraction
schema — the same treatment `spec.extra` already gets. The LLM proposes,
the validator decides; an unknown `specs` key is dropped with a warning on the
run rather than failing it (the `_assign_manufacturer` precedent).

**What this costs, accepted knowingly:**

1. **No filtering by trim, and no filtering *on* trim specs.**
   `catalogue_search` matches the base row's `motorbike_specs` only, so a
   30 l Adventure is invisible to a "≥ 25 l tank" filter. This is D4 — see §9.
2. **No FK to a trim.** No chunk, image, recommendation card or preference can
   be scoped to a trim; a card carries the trim as text.
3. **Trim specs are not drift-checked** the way `motorbike_specs` columns are,
   because they are not columns.

What it buys is the thing the owner asked for: one row per machine an advisor
would actually recommend, no row explosion, and the trim information present
and readable where it belongs.

### 2.6 What is deliberately *not* in this proposal

- **`emission_standard` and `licence_class` as enums** (the doc's field
  assignment section). Not in the frozen spec set; adding them is a separate
  change with its own blast radius through extraction, tools and the review
  form. Filed as OQ-9.
- **A `model_years` table.** Colours, packages and per-year prices are not
  something this catalogue advises on; the year *range* is on the row, and a
  colour package is a `variants` entry with a `description`.
- **An `aliases` table** (D3, §2.3).
- **A `buildinglines` table** (D6, §2.1).
- **Any admin CRUD for manufacturers.** Get-or-create through ingestion plus
  the review form is the whole write surface, as in 2b.

---

## 3. Identity, slug and duplicate rejection

**Identity** = `(manufacturer_id, model_name, year_from)`. No variant segment
(D2) and no type-code segment (D5): with several codes per row there is no
non-arbitrary way to pick one, and an identity that changes when an admin
adds a code is not an identity. The `buildingline` is a grouping, never part of
the identity — a model that changes family does not become a different
machine.

**Slug** — path-shaped, as the doc proposes, built from the parts and never
typed by a human:

```
{manufacturer-slug}/{model-slug}/{year-range-slug}

bmw/r-1300-gs/2023-
bmw/r-1250-gs/2019-2023
yamaha/mt-07/2025-
honda/cb750-hornet/2023-
```

The domain doc's example slug `bmw/r-1300-gs/k81/adventure` carries both a
trim and a type code; under D2 no trim is addressable and under D5 no single
code is canonical, so the slug ends at the year range. That is also the segment
a human can read, which the type code never was.

Slashes are safe: slugs never appear in a URL path today (SPA routes and API
routes address a ULID). The generation segment is `{year_from}-{year_to or ""}`;
a row without `year_from` cannot be approved (§4.2).

**Provisional slugs.** A backlog row created from a typed name has no identity
yet, so it keeps today's behaviour: `slug = slugify(query_name)` — no slashes.
The slug is **recomputed** when the identity is assigned. That is safe because
no row anywhere stores a slug (only `get_by_slug` and `resolve_name` read it),
and it is the point at which duplicates surface: recomputing into an existing
slug raises `DuplicateModelError`, and an admin merges the two backlog rows.
The invariant to pin: *an `approved` row always has a canonical (slash-shaped)
slug.*

**What this does not catch.** "R1300GS" and "R 1300 GS" typed as two backlog
entries slugify differently and are two rows until extraction gives them the
same `model_name`. That is the correct place to catch it — extraction, then
the recompute-on-assign collision — not a constraint.

---

## 4. Services

### 4.1 New: buildingline normalisation helper

Not a service — one function next to `product_service`, since there is no table
to own (D6):

```python
async def normalise_buildingline(session, manufacturer_id: str,
                                 name: str | None) -> str | None
async def list_buildinglines(session, manufacturer_id: str) -> list[str]
```

`normalise_buildingline` trims, collapses whitespace, returns `None` for empty,
and otherwise reuses the casing of an existing case-insensitive match under
that manufacturer (§2.1). `list_buildinglines` backs the review form's
`Autocomplete` and any future facet. Both are reads plus a pure transform — no
writes, no commits, no race handling to get wrong.

### 4.2 Changed: `backend/app/services/product_service.py`

- `create_backlog(session, name)` — writes `query_name` + provisional slug.
  Otherwise unchanged.
- **New** `assign_identity(session, motorbike, *, manufacturer_id,
  buildingline, model_name, year_from, year_to, type_codes, variants)` —
  `buildingline` passes through `normalise_buildingline` first;
  full-object replace of the identity block, recomputes the slug, commits,
  announces `product.updated`. Raises `DuplicateModelError` on slug collision.
  This is the only writer of those columns; the API PATCH and extraction both
  go through it.
- `transition(..., APPROVED)` — new guard *before* the transaction: a row
  without `manufacturer_id`, `model_name` or `year_from` raises a new
  `IncompleteIdentityError`, mapped
  to a 422 `incomplete-identity` at the API boundary. Reason: `approved` is
  the customer-visible surface, and the doc's rule is "store and display
  always as an unambiguous name" — a row that cannot render one has no
  business being published.
- A `CHECK` constraint backs the guard (`status <> 'approved' OR
  (manufacturer_id IS NOT NULL AND model_name IS NOT NULL AND
  year_from IS NOT NULL)`), added after the backfill (§7). Simpler than the
  earlier two-branch version, because the year range is now the only generation
  segment.

### 4.3 Changed: `backend/app/services/catalogue_search_service.py`

- `resolve_name` gains one leg, so the order becomes **exact slug → type code
  → substring**. The type-code leg matches the normalised input against
  `type_codes` (D5) and, as a retrieval hint only, against
  `suggestion->'type_codes'`; it returns the single row when exactly one
  matches and `None` when several do, so an ambiguous code falls through to
  the substring leg rather than guessing. The substring leg now searches
  `query_name` *and* `model_name` (a customer writes the model, an admin typed
  the whole phrase). Everything else is unchanged, including "approved only"
  and "`None`, never an exception". No alias leg (D3).
- `BrowseSort.NAME` can no longer sort on a display column. It becomes the
  composite `(manufacturer.name, model_name NULLS LAST, year_from, id)`,
  which is what an alphabetical catalogue actually wants. The wire value
  `sort=name` is unchanged.
- `VerifiedSpecs` and `BrowseRow` carry `NameParts` instead of a `name`
  string, so callers can render in their own context (§5). Their `name`
  attribute survives as a rendered convenience for the no-context caller.

### 4.4 New: `backend/app/services/naming_service.py`

See §5. Pure functions plus one batched read helper; no writes, no commits.

---

## 5. Rendering: the escalation algorithm

The database stores parts. Exactly one module turns parts into a string, on
the server, so every surface (tools, API, CLI) renders identically and the
frontend never formats a name.

Under D2 the domain doc's level 2 (`+ Variant`) has no data behind it: a row
has no variant name of its own. Under D5 its level 4 (`+ Type code`) has no
single value to print and is internal anyway. The escalation is therefore three
levels — buildingline, model, model + year range — and both trims and type
codes are shown as their own UI elements next to the name, never inside it.

```python
class NameLevel(IntEnum):
    BUILDINGLINE = 0   # never returned by render_name; headings only
    MODEL        = 1   # "BMW R 1300 GS"
    YEAR_RANGE   = 2   # "BMW R 1250 GS (2019–2023)" — the highest level there is

@dataclass(frozen=True, slots=True)
class NameParts:
    motorbike_id: str
    manufacturer: str | None
    buildingline: str | None
    model_name: str | None
    year_from: int | None
    year_to: int | None
    query_name: str

async def load_name_parts(session, motorbike_ids: Sequence[str]) -> dict[str, NameParts]
def render_name(parts: NameParts, *, context: Sequence[NameParts] = (),
                min_level: NameLevel = NameLevel.MODEL) -> str
def render_names(parts: Sequence[NameParts], *, min_level=NameLevel.MODEL) -> dict[str, str]
def render_buildingline(parts: NameParts) -> str | None   # level 0, headings/facets only
```

**Algorithm**

1. `model_name is None` → return `query_name` verbatim. Nothing structured
   exists; never invent a name. (This fallback is what keeps most of the
   existing test suite green through the migration.)
2. Start at `max(MODEL, min_level)`; render.
3. **Ambiguous?** — computationally: another member of `context` with a
   different `motorbike_id` renders the *same string at the current level*.
   If not ambiguous, return.
4. Escalate to `+ year range` and re-test, against the colliding subset only.
5. Year range renders `(2019–2023)`, `(from 2023)` when `year_to is None`,
   and is skipped when `year_from is None`.
6. Still colliding after the year range (identical manufacturer, model and
   year range on two rows — a data bug, since that tuple is the identity):
   append the last 6 characters of the id, deterministic, and
   `logger.warning`.

**"Ambiguous in the target context" is the caller's set, not the database.**
`render_name` never queries. The caller passes the rows it is about to show
together, because that is exactly what the doc means by "the target context
decides"; a database-wide uniqueness check would make every name maximally
long on every screen. Default `context=()` means "no context known" → renders
at `min_level`.

| Caller | context | min_level |
|---|---|---|
| `catalogue_search` tool | the returned rows | MODEL |
| `spec_comparison` tool | the compared rows | YEAR_RANGE |
| `licence_fit_check`, `cost_estimator` | `()` (one bike) | YEAR_RANGE |
| `present_recommendations` | the presented batch | YEAR_RANGE |
| `GET /api/catalogue-models` (list) | the page | MODEL |
| `GET /api/catalogue-models/{id}` (detail) | `()` | YEAR_RANGE |
| `GET /api/products` (admin) | `()` | MODEL — plus `queryName` shown verbatim next to it |

`YEAR_RANGE` as the floor for anything a customer is told to remember is the
doc's user-guidance rule. Level 0 is never a machine's name:
`render_buildingline` exists for group headings and catalogue facets only.

**Type codes in the UI.** Admin surfaces only, as a chip per code next to the
name (display spec §6.1). A customer payload does not carry them at all.

**Trims in the UI.** Where a trim matters (catalogue detail, spec comparison,
the review screen) the surface renders the `variants` entries as their own
element — a chip row or list with the `description`, and the delta specs shown
against the base column. The display spec
([`model-naming-display-spec.md`](model-naming-display-spec.md) §6.5) owns the
layout.

---

## 6. Blast radius

| Area | Files | What breaks / changes |
|---|---|---|
| ORM | `backend/app/db/models/motorbike.py` | column rename + 3 new columns (`buildingline`, `type_codes`, `variants`); **no new table** |
| Ingestion | `backend/app/services/ingestion/service.py` | `self.motorbike.name` → `query_name` at the Wikipedia and search calls (mechanical, 2 sites) |
| Extraction schema | `backend/app/llm/extraction.py`, `backend/app/llm/prompts/spec_extraction.md` | `NON_SPEC_FIELDS` grows from `("manufacturer",)` to also carry `buildingline`, `model_name`, `year_from`, `year_to`, `type_codes`, `variants`; new validators (year plausibility, type-code shape/cap/normalisation, variant list caps, variant `specs` key whitelist); new `to_identity_values()`. `to_spec_values` and `SPEC_FIELDS` are untouched. Prompt gains the doc's two pitfalls verbatim (displacement in the name ≠ displacement; never invent a type code — list every code the sources print, invent none) plus the variant rule: **base specs on the row, deltas only in `variants`** |
| Extraction service | `backend/app/services/spec_extraction_service.py` | `_assign_manufacturer` → `_assign_identity`: manufacturer get-or-create, buildingline normalisation, `assign_identity`. Same "never at the cost of the run" policy |
| Catalogue writes | `backend/app/services/product_service.py` | `create_backlog`, new `assign_identity`, approval guard, slug recompute, buildingline normalisation helper |
| Resolution / search | `backend/app/services/catalogue_search_service.py` | type-code leg; two-column substring; composite name sort; read models carry parts |
| Retrieval / chunks | `backend/app/services/retrieval_service.py`, `chunking.py`, `chunk.py` | **nothing** — provenance hangs off `motorbike_id`, which does not move |
| Tools (8) | `backend/app/llm/agents/tools/*` | `catalogue_search`, `spec_comparison`, `licence_fit_check`, `cost_estimator`, `present_recommendations`: their `name` field is now *rendered in context* — **the pinned camelCase result shapes stay byte-compatible**, only the values improve. `spec_comparison` additionally may surface trims as text. `flag_unknown_bike`: writes `query_name` (unchanged behaviour). `retrieve_bike_knowledge` and `record_preference`: unchanged |
| Tool service layer | `fit_check_service.py`, `cost_estimator_service.py` | their `name` comes from `VerifiedSpecs`; one-line change each |
| API schemas | `backend/app/api/schemas/products.py`, `catalogue_models.py` | **additive**: `buildingline`, `typeCodes` (array), `variants`, `queryName` on products; `variants` on the catalogue detail. `name` keeps its key and becomes rendered; `slug` becomes path-shaped; `modelName`/`yearFrom`/`yearTo` stop being permanently `null`. New writable `identity` block on `PATCH /api/products/{id}` — without it nothing can correct a bad extraction |
| API endpoints | `backend/app/api/endpoints/products.py`, `catalogue_models.py` | resolve parts, render, serialise |
| Typed client | `frontend/src/api/types.ts` (generated) | `make generate-api`; additive, so no compile break |
| Frontend | `AdminBacklogRoute.tsx`, review screen, `ModelSpecsPanel.tsx`, catalogue detail | `AdminBacklogRoute` already renders `manufacturer + modelName` and a year range — it starts showing real values with zero code change. New: an identity form section on the review screen, variant chips + delta specs on the catalogue detail |
| Seeds / fixtures | `backend/app/cli/data/seed_models.json` (unchanged — those are `query_name`s) | none |
| CLI | `backend/app/cli/catalogue.py` | new `backfill-identity`; optional `render-name` for debugging |
| Tests | ~9 backend files constructing `Motorbike(name=…)`, `test_catalogue_search_service.py` (sort order), tool tests asserting `name` | mechanical `name=` → `query_name=`; the `query_name` fallback in `render_name` keeps assertions that do not set an identity green **by design** |
| Docs | `docs/modules/ingestion.md`, `docs/modules/model-naming.md`, `README.md`, `docs/core-requirements-checklist.md` | identity section, CLI reference, cross-link |

Not affected at all: auth, chat persistence, the advisor loop, operations/SSE,
embeddings, images, the fencing layer.

---

## 7. Migration path

Nine steps, each landable in one agent session with green `make backend-test` /
`make frontend-test` and — where it carries a migration — a proven
`alembic upgrade head → downgrade -1 → upgrade head` round trip. Off head
`fb2747f937c4`. Step 6.1 is a pure refactor and ships alone, per the house
rule.

| # | Step | Agent | Verified by |
|---|---|---|---|
| **N1** | **Refactor only:** rename `motorbikes.name` → `query_name`. One `alter_column` migration; both product endpoints keep emitting `name` by reading `query_name`. No other change. | backend-dev | round trip; `make backend-test`; `curl -s localhost:8000/api/products \| jq` byte-identical to a pre-change capture |
| N2 | Schema: the three new `motorbikes` columns (`buildingline`, `type_codes`, `variants`) — **one** migration, no new tables, no writers, no API. Plus the buildingline normalisation helper and the `variants` / `type_codes` Pydantic models (shape, caps, normalisation, spec-key whitelist), each with tests. | backend-dev | round trip; `docker compose exec postgres psql -c '\d motorbikes'`; new helper + validator tests |
| N3 | `naming_service`: `NameParts`, `render_name`, `render_names`, `render_buildingline`, `load_name_parts`. Wired nowhere. Table-driven tests over the doc's own examples. | backend-dev | `make backend-test`; `app catalogue render-name <id> --context <id> <id>` prints the escalated name |
| N4 | Slug policy + `product_service.assign_identity` + `IncompleteIdentityError` guard + slug recompute. **No** CHECK constraint yet (existing rows would fail it). | backend-dev | `app catalogue set-identity …` then `psql -c 'select slug from motorbikes'` shows `bmw/r-1250-gs/2019-2023`; approving a row without a year range exits non-zero |
| N5 | Extraction: identity fields + `variants` in `ExtractedSpec` + prompt section; `_assign_identity` in `spec_extraction_service`. | backend-dev | `app ingest run "Yamaha MT-07"`, then `curl /api/products/<id>` shows `modelName`, `yearFrom`, `typeCodes`, `variants` |
| N6 | Backfill CLI `app catalogue backfill-identity` (deterministic, **never** re-ingestion — the 2b rule: re-ingesting deletes documents and embeddings). Sets `model_name = query_name` minus the known manufacturer prefix, recomputes slugs, and **prints a table of rows still missing a year range**. *Needs a human decision — see OQ-6.* | backend-dev | `--dry-run` on the seeded DB lists every row and what it would set; live run then `curl /api/products` shows populated `modelName` |
| N7 | The `CHECK` constraint (`approved ⇒ identity complete`), added `NOT VALID` then `VALIDATE`d in the same migration so a violating row fails the upgrade loudly. | backend-dev | round trip on a post-N6 database; an `UPDATE … SET model_name = NULL` on an approved row is rejected |
| N8 | Resolution + rendering wired in: the type-code leg, two-column substring, composite `BrowseSort.NAME`, read models carry `NameParts`, the five name-carrying tools and both JSON:API resources render in context. Wire keys unchanged. | backend-dev | `app tools run catalogue_search '{"categories":["adventure"]}'` shows year ranges only where two rows would otherwise collide; `app tools run cost_estimator '{"motorbikeName":"FLFBS"}'` resolves to the Fat Boy; `curl '/api/catalogue-models?sort=name'` ordered by brand then model; frontend suite still green (proves shape compatibility) |
| N9 | API `identity` block on `GET`/`PATCH /api/products` + `variants` on the catalogue detail + `make generate-api`; review-screen identity & variants section per the display spec; acceptance run; docs. | backend-dev → ui-ux-designer → frontend-dev → qa → docs-writer | `curl -XPATCH …` returns the recomputed slug; `pnpm typecheck` green; visible UI state: edit identity and variants, save, reload, values persist; QA proves a fresh ingest fills identity and a duplicate identity is rejected |

Step numbers are provisional (`N…`) because Phase 6 already uses 6.1–6.8 in
[`../roadmap.md`](../roadmap.md) for a different slicing; the architect assigns
final numbers when the phase is sliced. N1/N5/N6 overlap roadmap items 6.1/6.2
and should be merged with them, not run twice.

**The backfill's honest limits.** Today's `query_name` is free text and the
12 seeded models carry no year information at all. The CLI can derive
`model_name` mechanically (strip the manufacturer prefix it already knows
from the FK) but it **cannot** derive `year_from`, the type codes or the
buildingline. Recommended policy: the CLI does the mechanical part and
reports the gaps; an admin fills years through the review form, which is also
what the approval guard forces. Do not LLM-guess a year range into a
customer-visible name.

---

## 8. Open questions for the owner

Closed by the owner on 2026-08-31: **OQ-1** (generation = row → D1),
**OQ-5** (trims: JSONB with deltas, never a row → D2), **OQ-8** and **OQ-11**
(moot — no alias table, no trim filter → D3/D4), **OQ-4** and **OQ-12**
(settled by D5 and the owner's reaffirmation of D2), **OQ-3** (text column, not
a table → D6) and **OQ-13** (narrowed to spellings by D5, then accepted).
What remains below are standing recommendations, not blockers: they hold unless
the owner says otherwise.

| # | Question | Recommended default / status |
|---|---|---|
| OQ-2 | Enforce a complete identity before `approved` (service error + CHECK)? | **Yes.** Without it the structured identity stays optional and `query_name` remains the de-facto truth. |
| ~~OQ-3~~ | ~~Buildingline as its own table, or a nullable string column?~~ | **Closed: text column** (D6, §2.1). Drift is handled by a normalisation helper plus the review form's `Autocomplete`; promoting it to a table later is mechanical. |
| ~~OQ-4~~ | ~~Path-shaped slug or flat?~~ | **Closed.** Path-shaped, `{manufacturer}/{model}/{year-range}` — no type-code segment (D5). |
| OQ-6 | Backfilling year ranges for the seeded models: admin fills them, re-ingest, or LLM-guess? | Admin fills them through the review form. Re-ingestion deletes documents and embeddings (2b rule); an LLM guess would be an unverified number on a customer surface. |
| OQ-7 | `products.name` stays the *rendered* name (frontend untouched), or does `name` become `queryName` and a new `displayName` appear? | Keep `name` rendered, expose `queryName` additionally. It keeps the wire shape and the SPA compiles unchanged. |
| OQ-9 | `emission_standard` / `licence_class` as enums on the spec row, as the doc's field-assignment section asks? | Out of scope here; file as its own change. It is a frozen-spec-set change (extraction, tools, review form, drift guards) and unrelated to naming. |
| OQ-10 | Ambiguous customer input ("BMW GS"): a new `disambiguate_model` tool, or advisor-prompt handling on a multi-candidate resolver result? | Prompt handling. A ninth tool for a question the advisor can ask in prose is not worth the surface. |
| ~~OQ-12~~ | ~~A rendered name can no longer contain a trim.~~ | **Closed by the owner's reaffirmation of D2.** Names carry manufacturer, model and year range; trims and type codes are separate UI elements. Recorded in `docs/modules/model-naming.md`. |
| ~~OQ-13~~ | ~~Spellings (`R1300GS`) still depend on the advisor normalising them.~~ | **Closed: accepted for now.** Codes resolve through `type_codes`; spellings rely on the advisor plus `slugify`. Revisit when a transcript shows a real miss — the `aliases` JSONB column (§2.3) is then a one-step addition. |

### Two already-open questions this change touches

- **Phase-5 OQ "manufacturer names are inconsistent"** (`Kawasaki` vs
  `Kawasaki Motors`, filed 2026-08-29): with no alias table (D3), this is
  **not** closed here. Roadmap item 6.5 (normalise against the known-marque
  suggestion list) remains the fix.
- **Phase-5 OQ "`a2Eligible` is not cross-checked against power"**: unrelated
  to naming; leave it where it is.

---

## 9. Future upgrades

**Variant-aware filtering (D4).** `catalogue_search` and `SpecFilters` see the
base row's specs only. A customer asking for "at least a 20 l tank" will not
be shown a BMW R 1300 GS whose Adventure trim carries 30 l, and a hard
`seat_height_mm ≤ 800` filter will exclude a bike that offers a low-seat trim.
The same applies in reverse: a bike can pass a filter on a value the trim the
customer would actually buy does not have.

Sketch of the eventual fix, none of it in scope now:

- match `variants[].specs` alongside the base row — either a `jsonb_path_ops`
  GIN index with `@>`/`jsonb_path_exists` predicates, or a generated
  `min`/`max` column per filterable spec maintained on write;
- widen the tool result so a hit says *which* trim satisfied the filter,
  otherwise the advisor recommends a machine on a number the base does not
  have;
- decide the semantics deliberately: "any trim matches" (recall) vs "the base
  matches" (precision). The advisor should probably use the first and say so.

Recorded in [`../roadmap.md`](../roadmap.md) under "Future upgrades".

Also parked there: **promoting `buildingline` to a table** if a facet UI,
per-family content or an alias target ever needs one (distinct values become
rows, the column becomes an FK), an alias table if §2.3's trigger fires,
**per-trim type codes** (Harley's codes are really per trim, and the flat `type_codes` list
knowingly flattens that — the clean answer arrives with trim-aware filtering),
per-trim provenance (chunks/images scoped to a trim), and `model_years`.
