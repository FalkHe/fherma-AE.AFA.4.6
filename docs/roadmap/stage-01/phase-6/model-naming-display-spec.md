# Display Specification — Motorcycle Model Naming

**Binding for every surface that prints a motorcycle name**, customer and
admin. Produced by the ui-ux-designer against
[`../../modules/model-naming.md`](../../modules/model-naming.md), which is the domain authority —
where this spec and that document disagree, `model-naming.md` wins; report the
conflict, don't build either version.

This is a **display specification only**. It changes no code. It is written
against the *parts* of a name, not against today's `motorbikes.name` string,
and it assumes the concurrently-designed schema exposes those parts as separate
API fields (§1.1 lists exactly which). Until they exist, §11 pins the
degradation path.

Read first: [`../../general/frontend-stack.md`](../../general/frontend-stack.md),
[`phase-3/ui-spec.md`](../phase-3/ui-spec.md) (chat + tool-result conventions),
[`phase-4/ui-spec.md`](../phase-4/ui-spec.md) (catalogue conventions). The
conventions there continue to apply unchanged: MUI v6/v7, Material Design 2,
stock components only, palette tokens only, Material Symbols via `<Icon>`, all
chrome strings through react-i18next, no new dependencies.

The one rule everything below serves:

> Store the parts separately, render the shortest unambiguous name for the
> target context. Never a pre-built display string.

---

## 0.0 Owner decisions applied (2026-08-31)

This spec was first written against a four-level name that included the trim
(`BMW R 1300 GS Adventure`) and against an alias table. The owner decided
otherwise (see [`model-naming-data-model.md`](model-naming-data-model.md) §0);
the whole spec below is amended accordingly:

| Decision | What changed here |
|---|---|
| **A trim is never a row.** The catalogue row is the base; trims live in a `variants` JSONB with their spec deltas and a free-text `description`. | **A rendered name never contains a trim.** The old level 1 (`+ Variant`) is gone and the levels renumber: **0** buildingline, **1** model, **2** model + year range. Trims are their own UI element next to the name (§6.5), never words inside it. |
| **No alias table.** | The alias accordion (old §6.4) is dropped; §2.2's alias notice becomes conditional on the resolver ever reporting a rewrite. |
| **Trim-aware filtering deferred.** | Nothing here — noted so that a "20 l tank" filter returning a base row with 15 l reads as a known backend gap, not a display bug. |
| **No `buildinglines` table** — the family is a text column on `motorbikes`. | Nothing changes in the payload (`buildingline: string \| null`, as specced). The identity panel's `Autocomplete freeSolo` now reads that manufacturer's distinct values from the API, and it is the **only** thing standing between the catalogue and three spellings of `GS` — treat it as load-bearing, not a convenience. |
| **A generation may carry several type codes** (`FLSTF`, `FLFB`, `FLFBS` on one row), stored as a list and used for retrieval and resolution. | `typeCode` becomes `typeCodes: string[]`. Admin surfaces render **a chip per code** (§6.1); customer payloads still carry none. The name never contained a code and still never does. |

Type codes are still never part of a name: they are admin `Chip`s (§6.1). Levels
therefore stop at 2, and "the full form" everywhere below means
`{Manufacturer} {Model} ({year range})`.

---

## 0. Inventory — every place a name is printed today

Walked at `HEAD 2168707`. Each of these becomes a call site of the §1
contract; nothing else in `frontend/src/` prints a motorcycle name.

### Customer surfaces

| File | Line(s) | What is printed today | New level (§2) |
|---|---|---|---|
| `frontend/src/components/CatalogueModelCard.tsx` | 105 | `model.name` as `subtitle1` card title | 1, +2 in tail line |
| `frontend/src/components/CatalogueModelCard.tsx` | 98 | `alt={model.name}` on `CardMedia` | 2 (a11y form) |
| `frontend/src/components/CatalogueModelCard.tsx` | 64–69 | `manufacturer · category` subtitle | manufacturer moves into the name |
| `frontend/src/routes/CatalogueModelRoute.tsx` | 188–190 | `name` in the `Breadcrumbs` crumb | 1, `aria-label` 2 |
| `frontend/src/routes/CatalogueModelRoute.tsx` | 192–194 | `name` as `h4`/`h1` | 2, composed (§7.1) |
| `frontend/src/routes/CatalogueModelRoute.tsx` | 200–204 | standalone `manufacturer` line | removed — absorbed by the `h1` |
| `frontend/src/routes/CatalogueModelRoute.tsx` | 227 | `name` prop into the gallery | 2 (a11y form) |
| `frontend/src/components/ModelImageGallery.tsx` | 50, 71 | group `aria-label`, image `alt` | 2 (a11y form) |
| `frontend/src/components/RecommendationCard.tsx` | 110 | `recommendation.name` as `subtitle1` | 1, +2 in tail line |
| `frontend/src/components/RecommendationCard.tsx` | 103 | `alt` | 2 (a11y form) |
| `frontend/src/components/ToolResultCatalogueSearch.tsx` | 60 | `hit.name` as `ListItemText` primary | 1, +2 in `secondary` |
| `frontend/src/components/ToolResultSpecComparison.tsx` | 38–40 | `bike.name` as `nowrap` column header | **2, wrapping** (§4.3) |
| `frontend/src/components/ToolResultBlock.tsx` | 212 | `result.name` in `unknownBikeFlagged` | verbatim customer input (§2, row "flagged") |
| `frontend/src/components/ToolResultBlock.tsx` | 92–137 | `GenericToolResult` prints raw result JSON | verbatim, unchanged |
| `frontend/src/components/ToolResultLicenceFitCheck.tsx` | 43, 46 | `rule.label` / `rule.evidence` | server-composed, verbatim (§10) |
| `frontend/src/components/ToolResultCostEstimator.tsx` | 59 | `item.label` | server-composed, verbatim (§10) |
| `frontend/src/components/MessageSources.tsx` | 118–128, 59–65 | source titles and heading paths | retrieved content, verbatim — **never** re-rendered |
| `frontend/src/components/MessageBubble.tsx` → `UntrustedMarkdown.tsx` | — | names inside assistant prose | not renderable by this contract (§10) |
| `frontend/src/routes/ConsultationChatRoute.tsx` | 307–310, 365–367 | chat title (user's first message) | verbatim user text |
| `frontend/index.html` | 7 | static `<title>` | replaced per route (§2, row "page title") |

### Admin surfaces

| File | Line(s) | What is printed today | New level (§2) |
|---|---|---|---|
| `frontend/src/routes/admin/AdminBacklogRoute.tsx` | 64–70 | `displayName()` — `manufacturer + modelName`, else the typed `name` | **delete**; replace with the §1 contract at 2 |
| `frontend/src/routes/admin/AdminBacklogRoute.tsx` | 72–79 | `yearRange()` — `2006–` caption | **delete**; the year range is part of the name now (§1.3) |
| `frontend/src/routes/admin/AdminBacklogRoute.tsx` | 156–161 | model cell | 2 + type-code chips (§6.1) |
| `frontend/src/routes/admin/AdminBacklogRoute.tsx` | 168 | `OperationProgress name=` | 1 (a11y label, §8) |
| `frontend/src/routes/admin/AdminModelReviewRoute.tsx` | 270 | breadcrumb crumb | 1, `aria-label` 2 |
| `frontend/src/routes/admin/AdminModelReviewRoute.tsx` | 277–279 | `row.name` as `h5`/`h2` | 2 + type-code chips |
| `frontend/src/routes/admin/AdminModelReviewRoute.tsx` | 203, 244 | `OperationProgress name=` | 1 |
| `frontend/src/components/ModelImagePanel.tsx` | 139, 150 | `alt={product.name}` | 2 (a11y form) |
| `frontend/src/components/AddModelDialog.tsx` | 117–132 | the free-text name field | raw admin input (§6.4) |
| `frontend/src/components/OperationProgress.tsx` | 46 | `admin.backlog.progressLabel` | receives an already-rendered string |

Two of these are load-bearing and easy to miss: `AdminBacklogRoute`'s local
`displayName()` is exactly the pre-built-string anti-pattern the domain doc
forbids, and `ToolResultSpecComparison`'s `whiteSpace: "nowrap"` header is the
one place a long name is guaranteed to overflow.

---

## 1. The rendering contract

### 1.1 Fields the frontend needs

Every API payload that identifies a motorcycle — catalogue list item,
catalogue detail, admin product row, `catalogue_search` hit,
`spec_comparison` bike, `present_recommendations` card — must carry **these
members, individually**. This is the frontend's requirement on the architect's
schema work; a payload missing them cannot be rendered correctly by any level
above 1.

| Member | Type | Example | Required for |
|---|---|---|---|
| `manufacturerName` | `string` | `"BMW"` | every level |
| `buildingline` | `string \| null` | `"GS"` | level 0 only |
| `modelName` | `string` | `"R 1300 GS"` | levels 1–2 |
| `yearFrom` | `number \| null` | `2024` | 2 |
| `yearTo` | `number \| null` | `null` = still in production | 2 |
| `nameQualifier` | `string \| null` | `"Euro 5+"` | 2, optional (§12 Q4) |
| `typeCodes` | `string[]` | `["FLSTF", "FLFB", "FLFBS"]` | **admin surfaces only**, one chip per entry — never inside the name. `[]` is normal |
| `variants` | `{ name, description?, specs? }[]` | `[{ name: "Adventure", … }]` | **not part of the name** — its own element (§6.5) |
| `displayLevel` | `0 \| 1 \| 2` | `2` | the server's ambiguity verdict (§1.4) |

`typeCodes` must **not** be present in customer payloads. Not "present and
unused" — absent. A field the client holds is a field that leaks into a
tooltip, a `title` attribute or a DOM dump eventually, and the domain doc is
explicit that type codes stay internal.

### 1.2 The function

New module, flat in the components directory per the landed convention, mirroring
the shape of the existing `frontend/src/components/specFields.ts` (which takes
`t` as its first argument — same pattern, no new idiom):

```
frontend/src/components/modelName.ts

export type ModelNameParts = { …the §1.1 members, minus displayLevel… };
export type NameLevel = 0 | 1 | 2;

formatModelName(t, parts, level)      → string   // the visible form
formatModelNameA11y(t, parts)         → string   // the level-2 spoken form (§8)
formatYearRange(t, parts)             → string | null
resolveNameLevel(parts, serverLevel, minLevel) → NameLevel
```

Pure functions, no hooks, no React. `t` is passed in because the year-range
connectives are words (`from 2024`, `until 2016`) and words are translated;
manufacturer, model and trim strings are **verbatim** and never translated —
the same standing i18n exemption as source titles and spec enum raw values.

Composition, given a resolved level:

| Level | Composition | Example |
|---|---|---|
| 0 | `{manufacturerName} {buildingline}` | `BMW GS` |
| 1 | `{manufacturerName} {modelName}` | `BMW R 1300 GS` |
| 2 | level 1 `+ " (" + yearRange[, qualifier] + ")"` | `BMW R 1300 GS (from 2024)` |

`resolveNameLevel` clamps: level 0 with `buildingline === null` falls to 1;
2 with `yearFrom === null && yearTo === null` falls to 1. A clamp is silent, never an error and never a
placeholder — the doc's rule is "shortest *unambiguous*", and a parenthesis
around nothing is neither.

### 1.3 Year range

| `yearFrom` | `yearTo` | Rendered | i18n key |
|---|---|---|---|
| 2019 | 2023 | `2019–2023` (en dash, no spaces) | `common.modelName.yearRange` |
| 2024 | `null` | `from 2024` | `common.modelName.yearFrom` |
| `null` | 2016 | `until 2016` | `common.modelName.yearUntil` |
| 2021 | 2021 | `2021` | `common.modelName.yearSingle` |
| `null` | `null` | — (level clamps to 1) | — |

With a qualifier: `from 2025, Euro 5+` inside the same parentheses —
`Yamaha MT-07 (from 2025, Euro 5+)`, exactly the doc's example.

A **single year is never rendered as the name**. `yearTo === null` means "still
in production", not "one model year". The doc's rule stands verbatim: year
range = which motorcycle, single year = which execution — and we do not model
executions.

### 1.4 Who decides the level

**The server decides, per result set; the client may only escalate.**

```
effectiveLevel = clamp(max(payload.displayLevel, surface.minLevel))
```

- **Server**, because ambiguity is a property of the *candidate set*, and only
  the server sees the set. A catalogue page shows 24 of N models; the client
  cannot know that page 3 holds an `R 1250 GS` that makes page 1's `R 1300 GS`
  need its year range. The same is true of every tool result, which the agent
  builds server-side. A pure client rule would be wrong on exactly the cases
  that matter.
- **Not a pre-built string**, because that is the one thing the domain doc
  forbids, and because the same row is rendered at three different levels
  across a card, a breadcrumb and a chip.
- **The client may escalate** (`minLevel`) but never de-escalate. A surface
  knows things the server does not: a comparison table exists *because* two
  bikes are being told apart, so it pins `minLevel: 2` regardless of what the
  server thought. De-escalation is forbidden because it can only ever remove a
  disambiguator the server judged necessary.
- **Persisted snapshots** (recommendation cards, tool results stored on a
  message) keep the `displayLevel` they were written with. A name in a
  three-month-old transcript must read as it did then; re-deriving it against
  today's catalogue would silently rewrite history.

If `displayLevel` is missing from a payload (older persisted message, a tool
this frontend predates), the client uses `surface.minLevel` and never less than
1. Level 0 is never a fallback — the doc: *never for an individual machine*.

### 1.5 The one new component

`frontend/src/components/ModelNameText.tsx` — a thin wrapper that renders stock
`Typography` (optionally `Tooltip`), and exists for exactly one reason: the
pairing of *visible truncated form* + *`aria-label` full form* + *tooltip* must
be identical at 20 call sites, and copy-pasting it 20 times is how one of them
ends up without the `aria-label`. It adds no styling of its own.

```
<ModelNameText
  parts={…}            // §1.1
  level={…}            // resolved by the caller via resolveNameLevel
  variant="subtitle1"  // any Typography variant
  component="h2"
  layout="inline" | "stacked"   // §4.1
  tooltip={boolean}    // default: true when level < 2
/>
```

Everything else in this spec uses stock MUI: `Typography`, `Chip`, `Tooltip`,
`Breadcrumbs`, `TableCell`, `Card`, `Autocomplete`, `List`.

---

## 2. Per-surface rules

Every row below is a call site of `formatModelName`. "Level" is the
`minLevel` the surface pins; the server may push it higher.

| # | Surface | minLevel | Rendered form | Notes |
|---|---|---|---|---|
| 1 | Chat message text (assistant prose) | — | whatever the model wrote | Not renderable client-side (§10). The backend must hand the agent level-2 names in tool payloads so it copies a correct form. |
| 2 | Recommendation card title | 1 | `BMW R 1300 GS` | Stacked (§4.1); year range on the tail line. |
| 3 | Recommendation card tail line | 2 | `from 2024 · BMW` | `caption`, `text.secondary`. |
| 4 | Catalogue card title | 1 | `Honda CRF1100L Africa Twin` | Stacked, 2-line clamp. |
| 5 | Catalogue card subtitle | 2 | `from 2022 · adventure` | Year range **first** — it is the disambiguator; category follows. |
| 6 | Catalogue detail `h1` | 2 | `BMW R 1300 GS (from 2024)` | Composed with per-part weighting (§7.1). Never truncated, always wraps. |
| 7 | Comparison table column header | **2** | `BMW R 1250 GS`<br>`(2019–2023)` | Wraps to two lines; `nowrap` removed (§4.3). |
| 8 | `catalogue_search` result row | 1 | `Kawasaki Z900` primary | Year range joins the existing `secondary` spec summary: `2020–2024 · naked · 92 kW`. |
| 9 | `licence_fit_check` / `cost_estimator` labels | — | server-composed, verbatim | Backend composes them at level 2 (§10). |
| 10 | Source / citation chip | — | **never a model name** | Sources carry document title + URL (§5). If a *filter* chip names a model (admin `?sameNameAs=`), level 1 + tooltip. |
| 11 | `flag_unknown_bike` caption | — | the customer's own words, verbatim | `Noted: "my 1250"` — quoting is the point; never normalise. |
| 12 | Disambiguation option card (§5) | **2** | `BMW R 1250 GS (2019–2023)` | Full form always, never truncated — the whole card exists to tell two names apart. |
| 13 | Admin backlog list row | **2** | `BMW R 1300 GS (from 2024)` + `K81` chip(s) | Admins need the year range on every row; a backlog spans generations by construction. |
| 14 | Admin review header `h2` | **2** | same, + one chip per type code | |
| 15 | Admin identity panel preview | 1 and 2 | both shown at once | §6.2 — the admin sees what the customer will see. |
| 16 | Breadcrumb (customer + admin) | 1 | `BMW R 1300 GS`, ellipsized if it must be | `aria-label` and `title` carry level 2; the `h1` right below is the full form, so the crumb may truncate. |
| 17 | Page `<title>` | **2** | `BMW R 1300 GS (from 2024) — Motorcycle Buying Advisor` | §2.1. |
| 18 | Search input (catalogue, if added) | — | the user's raw text, never rewritten | §2.2. |
| 19 | Admin add-model dialog field | — | the admin's raw text | §6.4. |
| 20 | Empty state after a filtered search | 3 | `No model matches "BMW R 1250 GS (2019–2023)"` | Only when the query *resolved* to a model. A free-text miss quotes the raw input instead. |
| 21 | Error state on a model page | — | **no name at all** | If the fetch failed we do not know the name; `Skeleton` in the header slot, generic error body. Printing a stale name over an error is a lie. |
| 22 | Image `alt`, gallery `aria-label`, progress `aria-label` | 2 (a11y form) | `BMW R 1300 GS, from 2024` | §8 — spoken form, no parentheses, no en dash. |

### 2.1 Page title

There is no `document.title` management today (only the static
`frontend/index.html` line 7). Add a `useDocumentTitle(text)` hook —
`useEffect` writing `document.title`, restoring on unmount — used by the four
detail routes.

Level **3 always**. This looks like a violation of "shortest unambiguous", and
is the opposite: the target context of a browser tab strip is *every page the
user has open*, which is the most ambiguous context that exists. Shortest
unambiguous there is the full form.

Format: `{level-2 name} — {t("app.name")}`. Chat: `{chat title} — {app name}`.
List routes: `{t("catalogue.list.title")} — {app name}`.

### 2.2 Search input

The customer catalogue currently has filters only, no free-text search
(`useCatalogueFilters.ts`), so this is a rule for when one is added rather than
a change to build now:

- The input **echoes the user's text verbatim**. Never rewrite `GS1300` into
  `R 1300 GS` in the field — a field that edits itself under the cursor is the
  single most-hated input behaviour there is.
- Matching goes through the server's resolver (exact slug, then substring —
  there is no alias table, D3). The result list renders at the server's
  `displayLevel`, which for a loose query will be 2.
- **If and only if** the backend ever reports that it rewrote the query, one
  `Alert severity="info"` line above the results: `Showing results for BMW R
  1300 GS`, with the raw query quoted. Today no such rewrite exists, so the
  line does not render; keep the key, build the line when a rewrite is
  reported. It would be non-destructive either way.
- No-match empty state quotes the raw query and suggests the buildingline:
  `No model matches "GS1300". Try "BMW GS".`

---

## 3. States

Every surface keeps the loading / empty / error treatment its own ui-spec
already pins. Naming adds three rules:

**Loading.** A name is skeletoned at the width of its *level-2* form, not its
truncated one — `Skeleton variant="text" width="60%"` in the card title slot,
`width={280}` in the detail `h1` slot. A skeleton sized for a short name that
is replaced by a long one is the layout jump the existing specs work hard to
avoid. The catalogue's reserved `LinearProgress` slot
(`CatalogueRoute.tsx:250`) and the admin `OperationProgress` are unchanged;
they remain the grading-relevant progress indicators.

**Empty.** Never render an empty parenthesis, an empty variant slot, or a
placeholder dash inside a name, and never an empty trim element. A missing
part clamps the level (§1.2). The
existing "null discipline" comment in `CatalogueModelCard` states the same rule
for specs; this extends it to the name.

**Error.** Row 21 above: a failed load prints no name. A *partially* failed
load — the model resolved but its trims did not — renders at the level its
present parts support, which is the clamp again, not an error state.

---

## 4. Truncation and density

`Honda CRF1100L Africa Twin Adventure Sports DCT (from 2022)` is 58
characters. It will not fit anywhere at `subtitle1` on a phone. The governing
rule:

> **The disambiguator is the tail.** The year range is the last thing on the
> line and the load-bearing one. Tail-ellipsis on a level-1/3 name deletes exactly
> the information the level exists to add. So: never `noWrap` on a level-1 or
> level-2 name unless a full form is available elsewhere on the same screen.

**Minimum legible fragment: level 1** — `{Manufacturer} {Model}`. No surface
may ever show less. If level 1 does not fit, the container is wrong, not the
name.

### 4.1 Two layouts

`ModelNameText` renders one of two shapes:

- `layout="inline"` — one run, wrapping allowed. Used in the detail `h1` and
  the disambiguation cards.
- `layout="stacked"` — the model on line 1, the year range on line 2 as
  `Typography variant="caption" color="text.secondary"`. Used in every card
  and list row. This is how a long name survives a 280px card without losing
  its tail.

### 4.2 Per-container

| Container | MUI | Behaviour |
|---|---|---|
| Card title (catalogue, recommendation) | `Typography variant="subtitle1"` | **Remove `noWrap`.** Two-line clamp: `sx={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}`. Stacked layout, so the clamp only ever eats model text, never the year range on the line below. |
| Card tail line | `Typography variant="caption"` | `noWrap` **allowed** — it is short by construction (`from 2022 · BMW`). |
| `Chip` | `Chip size="small"` | A chip cannot wrap. Chips therefore carry **level ≤ 1 only**; the level-2 form goes in `aria-label` + `Tooltip`. `sx={{ maxWidth: 220 }}` and let MUI's built-in label ellipsis run. If the chip would show less than level 1, use a `Typography` instead of a chip. |
| Narrow table column (comparison header) | `TableCell` | §4.3. |
| Wide table cell (admin backlog "Model") | `TableCell` | Stacked layout, no truncation, column `minWidth: 240`. The table already scrolls at `minWidth: 720`. |
| Breadcrumb crumb | `Typography noWrap` inside `Breadcrumbs` | Truncation **permitted** here alone, because the `h1` immediately below carries the full form. Keep the existing `"& .MuiBreadcrumbs-li": { minWidth: 0 }` sx from `ConsultationChatRoute.tsx:361` — it is what makes the crumb shrink instead of scrolling the document. Add `title` + `aria-label` with level 2. |
| Mobile card (`xs`) | — | **No ellipsis at all.** Three-line clamp instead of two; a phone has vertical room and no hover, so a tooltip is not a fallback there. |
| Detail `h1` | `Typography variant="h4"` | Never truncated, always wraps, `overflowWrap: "anywhere"` guards a pathological single token. |

### 4.3 The comparison table header — the one real conflict

`ToolResultSpecComparison.tsx:38` pins `whiteSpace: "nowrap"` with
`COLUMN_WIDTH = 120`. At level 2 that overflows every time and the block
already scrolls horizontally inside the bubble. Change:

- Header cells: drop `whiteSpace: "nowrap"`, use the **stacked** layout — the
  model on line 1 (wrapping), year range on line 2 as `caption` /
  `text.secondary`.
- `COLUMN_WIDTH` 120 → **160**, so `minWidth` becomes `160 * (bikes + 1)`.
- The spec *rows* keep `nowrap` — those are short labels and numbers.
- The component's existing docstring rule stands and is reinforced: never drop
  a column, never truncate a header. A comparison that hides which generation
  it is comparing is worse than no comparison, and this table is the surface
  where two same-named generations most often sit side by side.

---

## 5. Ambiguity disambiguation (customer)

The domain doc: accept the input at buildingline level, ask back with picture,
year range and power — **never** type codes — then store and display the
unambiguous form.

### 5.1 Where it lives

**In the transcript, as a tool-result block.** Not a modal, not a sidebar.

Rationale, all three of which rule out a dialog: it must survive a page reload
(the transcript is persisted, a modal is not); it must not interrupt the
`seen → typing… → message` rhythm from `docs/general/architecture.md`; and answering it
has to be an ordinary user turn so the whole existing SSE/turn machinery
applies with zero new plumbing.

Mechanically: the ask-back is a `catalogue_search` result carrying
`ambiguous: true` and a `candidates[]` array (§12 Q7 — a flag on the existing
tool, not a new tool, so the agent loop is untouched). `ToolResultBlock.tsx`
gains one dispatch branch → `ToolResultDisambiguation.tsx`, inside the existing
`ToolResultFrame` (glyph `help`, label
`consultations.tools.disambiguate.title`). It renders like every other tool
result: always expanded, never behind a toggle.

### 5.2 Layout

```
┌ ❔ WHICH ONE DID YOU MEAN? ─────────────────────────────────┐
│ You said "my 1250".                                        │
│                                                            │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐                     │
│ │ [photo]  │ │ [photo]  │ │ [photo]  │   ← Card +          │
│ │ BMW      │ │ BMW      │ │ BMW      │     CardActionArea  │
│ │ R 1250 GS│ │ R 1300 GS│ │ F 850 GS │                     │
│ │          │ │          │ │          │                     │
│ │2019–2023 │ │from 2023 │ │2018–2023 │   ← Chip, outlined  │
│ │100 kW    │ │100 kW    │ │70 kW     │                     │
│ │(136 hp)  │ │(136 hp)  │ │(95 hp)   │                     │
│ └──────────┘ └──────────┘ └──────────┘                     │
│                                                            │
│ [ None of these ]        Browse all 6 GS models →          │
└────────────────────────────────────────────────────────────┘
```

- Container: `Stack direction="row" spacing={1} sx={{ overflowX: "auto" }}` on
  `xs`, `Grid container` from `sm` up. Reuses the recommendation-card idiom
  the customer has already seen in this transcript.
- Each option: `Card variant="outlined"` + `CardActionArea` (**not** a link —
  it sends a message), `CardMedia` with `srcSet` + `loading="lazy"` and the
  same `two_wheeler` `Icon` fallback as `RecommendationCard.tsx:85–95`.
- Name: `ModelNameText level={2} layout="stacked"`, never truncated.
- Year range: repeated as an outlined `Chip size="small"` — it is the primary
  selection criterion the doc names, so it gets chip weight, not caption
  weight.
- Power: `caption`, `text.secondary`, `100 kW (136 hp)` — kW **and** hp, per
  the domain doc's field-assignment rule.
- **No type code anywhere.** Not in text, not in a tooltip, not in `alt`, not
  in the DOM (§1.1: the payload does not contain it).
- Max **5** options. Beyond that, the trailing `Button` links to
  `/catalogue?manufacturer=…&…` with the count: `Browse all 6 GS models`.
- `Button` "None of these" always present.

### 5.3 Interaction and the SSE rhythm

Clicking an option composes a plain user message — the level-2 name, e.g.
`The R 1250 GS (2019–2023)` — and sends it through the existing
`useSendMessage(chatId)`. From that instant the standard rhythm runs
unmodified:

```
click → optimistic user bubble (state "sending")
      → server 201, bubble flips to "sent"  ("seen")
      → chat.activeOperationId set          → <TypingIndicator/>
      → SSE invalidation → refetch → assistant message renders
```

No new realtime path, no new loading component. "None of these" focuses the
composer with a prefilled draft instead of sending — the customer may not know
the answer, and forcing a message would be a dead end.

### 5.4 States

| State | Treatment |
|---|---|
| Loading (block itself) | None needed — the block only exists once its message is persisted. |
| Loading (after a click) | The existing optimistic bubble + `TypingIndicator`. The clicked card gets `disabled` immediately so a double-click cannot send twice. |
| Resolved (a later message exists) | All `CardActionArea`s `disabled`, `sx={{ opacity: 0.6 }}`, and the chosen one keeps `borderColor: "primary.main"`. An ask-back in scrollback is history, not a live control. |
| Empty `candidates[]` | Do not render cards. One `Typography variant="body2" color="text.secondary"`: `consultations.tools.disambiguate.noCandidates` — the assistant's own prose is then the ask-back. |
| Image missing on an option | `two_wheeler` `Icon` fallback, identical to the recommendation card. Never blocks the option. |
| Send failed | The existing failed-bubble path (`retry` / `discard` in `ConsultationChatRoute.tsx:230–246`). Nothing new. |
| Connection lost | The existing `LiveConnectionAlert`. |

---

## 6. Admin-only affordances

### 6.1 Type codes

A generation carries **zero or more** codes (`["FLSTF", "FLFB", "FLFBS"]`).
Visible to admins in three places, always as **stock `Chip`s**, one per code,
never concatenated into the name string:

```tsx
{typeCodes.map((code) => (
  <Chip key={code} size="small" variant="outlined"
        sx={{ fontFamily: "monospace" }}
        label={code}
        aria-label={t("admin.identity.typeCodeA11y", { code })} />
))}
```

1. Backlog row, in the Model cell, after the name.
2. Review header, in the existing `Stack` next to `MotorbikeStatusChip`.
3. The identity panel (§6.2), as an editable field.

Rules for a list rather than a single chip:

- **Empty renders nothing** — no chip, no dash, no "no type code" label. Most
  rows will have none for a while.
- **In a row context (backlog, review header) show at most 2**, then one
  `Chip` reading `+2` whose `Tooltip` lists the rest. Codes are a lookup aid,
  not a data display; three monospace chips push the year range off a narrow
  row. The identity panel (§6.2) always shows all of them.
- **Order is not meaningful** — render the stored order, never sort, never mark
  one "primary". The backend pins that nothing depends on order.
- `aria-label` spells each one out (`Type code K 81`) because a screen reader
  reads `K81` as a word otherwise. Monospace because these are codes and
  column alignment across rows is the point.

### 6.2 The identity panel — where variants and parts are edited

`AdminModelReviewRoute.tsx` has three tabs (`documents | specs | image`,
line 50). Add a fourth, **first** in order: `identity`. The default tab stays
`documents` (no behaviour change for existing links); `?tab=identity`
addresses it, matching the pinned search-param convention.

`frontend/src/components/ModelIdentityPanel.tsx`, same shape as the existing
`ModelSpecsPanel` (React Hook Form + Zod, dirty-state reported upward via
`onDirtyChange`, save is explicit):

```
┌ Identity ──────────────────────────────────────────────────┐
│ Manufacturer  [ BMW              ▾]   Autocomplete          │
│ Buildingline  [ GS               ▾]   Autocomplete freeSolo │
│ Model name    [ R 1300 GS         ]   TextField             │
│ Year from     [ 2024 ]  Year to  [    ]  helper: "empty =   │
│                                          still in production"│
│ Type codes    [ FLSTF ×][ FLFB ×][ FLFBS ×]   internal —    │
│               [ add code…          ]  not shown to customers │
│                                                             │
│ Trims  (this row is the base)                               │
│  ┌ Adventure ──────────────────────────────────── [🗑] ┐    │
│  │ Description [ Tubeless spoked wheels, big screen ]  │    │
│  │ Differs from base:  fuel_capacity_l [ 30 ]  [🗑]    │    │
│  │                     [ + spec ]                      │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌ Triple Black ───────────────────────────────── [🗑] ┐    │
│  │ Description [ Colour and equipment package       ]  │    │
│  └─────────────────────────────────────────────────────┘    │
│   [ + Add trim ]                                            │
│                                                             │
│ ── Preview ────────────────────────────────────────────────│
│  Level 1  BMW R 1300 GS                                     │
│  Level 2  BMW R 1300 GS (from 2024)                      │
│                                                             │
│              [ Discard ]  [ Save identity ]                 │
└─────────────────────────────────────────────────────────────┘
```

- Type codes: `Autocomplete multiple freeSolo` with `renderTags` producing the
  monospace chips of §6.1, values upper-cased on blur. Free-solo because codes
  come from sources, not from a list we hold. Helper text states what they are
  for — *retrieval and lookup, never shown to customers* — and the shape rule;
  a rejected entry (bad shape, over the cap of 8) shows inline `helperText`
  rather than silently vanishing. Duplicates are dropped on entry.
- Manufacturer: `Autocomplete` over the existing `/api/manufacturers` query
  (`queryKeys.manufacturers.list()`), not free text — manufacturers are a
  curated table.
- Buildingline: `Autocomplete freeSolo` over that manufacturer's distinct
  existing values, served by the API. Free-solo because new families appear.
  Because the backend stores this as free text with no table behind it (D6),
  **this suggestion list is the drift guard** — it is what stops `GS`, `gs` and
  `G S` from all existing. Two rules follow: the options must load before the
  field is usable (skeleton the field, do not render an empty `Autocomplete`
  that invites typing), and a typed value that case-insensitively matches an
  existing option must snap to the stored casing on blur, visibly, so the admin
  sees the join happen.
- Trims (the `variants` JSONB column): a `List` of `Card variant="outlined"`
  rows, each with a name `TextField`, a multiline `description` `TextField` and
  a small delta-spec editor — a `Select` over the known spec fields plus a
  value `TextField`, one row per differing spec, add/remove per row. **There is
  no base entry and no "which one is base" radio**: this catalogue row *is* the
  base, and its `motorbike_specs` are the base specs. A trim carries **only**
  what differs from or is added to the base; an absent field means "same as the
  base", never zero. Fields, **not** a JSON textarea — a raw JSON editor in an
  admin UI is how malformed arrays get saved. Order is the display order;
  drag-reordering is out of scope, an arrow `IconButton` pair is enough if
  ordering matters (§12 Q9).
- **The live preview is the point of the whole panel.** It renders both levels
  from the current form buffer through the same `formatModelName` the
  customer surfaces use. An admin who can see the level-2 form updating as they
  type will not invent a pre-built name, which is the failure mode the domain
  doc exists to prevent.
- States: loading = the route's existing `CircularProgress` gate; saving =
  `Button` with `CircularProgress size={20}` `startIcon` and disabled form (the
  landed `ModelSpecsPanel`/`AddModelDialog` pattern); error = inline
  `helperText` for 422 field errors, `Alert severity="error"` for anything
  else, with the typed values kept.
- Approve-dialog interaction: unsaved identity edits must feed the existing
  `hasUnsavedSpecs` warning path in `AdminModelReviewRoute.tsx:67` — rename the
  state to `hasUnsavedChanges` and OR the two panels' dirty flags. Approving
  while an unsaved name sits in a form buffer is exactly the mistake the
  warning exists for.

### 6.3 Seeing that two rows are the same name, different generation

In the backlog, when two or more rows share `manufacturerName + modelName`:

- Every one of those rows renders at level 2 (already the admin default, §2
  row 13) **and** shows its type-code chips. Consistency across the group is
  what makes them comparable at a glance.
- Each such row carries one extra `Chip size="small" variant="outlined"` with
  `<Icon>layers</Icon>` and the group size — `3 generations` — with a
  `Tooltip` listing the sibling year ranges.
- Clicking it sets `?sameName=<modelName>` in the URL (same
  `setSearchParams(..., { replace: true })` convention as the existing status
  filter), filtering the table to that group. The active filter is shown as a
  removable `Chip` above the table, next to the existing status select.
- Grouping is computed **server-side** and delivered as a `sameNameCount` on
  the row — the admin list is paginated (the hooks walk all pages, but the
  count must still be right for the whole table, not the current page).

### 6.4 Aliases — not built (deferred)

The first draft of this spec surfaced an alias table inside the identity panel.
The owner deferred aliases entirely (D3): the advisor LLM normalises "R1300GS"
before it calls a tool, and the resolver already absorbs case, spacing and
punctuation. **No alias accordion, no alias chips, no add field, no i18n
keys.**

If the backend later adds the `motorbikes.aliases` metadata column that
[`model-naming-data-model.md`](model-naming-data-model.md) §2.3 sketches, the
UI is a stock `Accordion` in this panel: a `Chip` per string with `onDelete`, a
`TextField size="small"` + Add button, collapsed by default with the count in
the summary. Spec it then; do not build it now.

### 6.5 Trims on customer surfaces

Trims are data, not name words. Where they appear:

- **Catalogue detail** — a `Chip` row directly under the `h1`, one outlined
  `Chip` per `variants` entry (`Adventure`, `Triple Black`), with the
  `description` as its `Tooltip`. The chips are labels; they link nowhere.
  Below, in `ModelSpecsPanel`, any trim carrying `specs` gets one line stating
  the difference against the base — `Adventure · 30 l tank, 268 kg` — composed
  from the deltas, so the customer reads *what differs*, never a second full
  spec sheet.
- **Cards, tool result rows, comparison headers** — no trims at all. They are
  already tight, and a trim list would compete with the year range, which is
  the disambiguator.
- **Never inside a name**, an `alt`, a breadcrumb or a page title. The one
  place trims appear in sentences is assistant prose, which this contract
  cannot reach (§10): the backend hands the agent the trim list in the tool
  payload and the model may mention it in words.
- Empty `variants` renders nothing — no heading, no "no trims" line.
- The delta specs are **not** filterable (backend gap D4). Never phrase a trim
  line so it reads like a filter promise.

`AddModelDialog` is unchanged in mechanics: the admin types a free-text name,
which remains the ingestion seed. Only its helper text changes — it should ask
for the marketing name (`e.g. BMW R 1300 GS`) and state that the
parts are edited after ingestion, in the identity tab.

---

## 7. Typography and hierarchy

Palette tokens only. The goal is that the eye lands on the **disambiguator**,
which is the year range — that is the part that changes the answer.

### 7.1 The detail-page `h1`

One `h1`, three weighted runs (`Box component="span"` inside the
`Typography`), replacing both the current `h1` and the separate manufacturer
line at `CatalogueModelRoute.tsx:200–204`:

| Run | Typography | Weight | Colour |
|---|---|---|---|
| `BMW` | `h4` (inherited) | 400 | `text.secondary` |
| `R 1300 GS` | `h4` | **600** | `text.primary` |
| `(from 2024)` | `h5`, `component="span"` | 400 | `text.secondary` |

The model is the heaviest run and the manufacturer deliberately is not: the
marque is what the customer already knows they are looking at. The year range
is one step smaller and secondary — metadata that must be *findable*, not
*loud*. The trim chips (§6.5) sit **below** this line and never compete with
it.

Colour is never the only signal: weight and size carry the same hierarchy, so
the h1 survives a monochrome or high-contrast rendering.

### 7.2 Everywhere else

| Surface | Model | Year range |
|---|---|---|
| Catalogue / recommendation card | `subtitle1`, `text.primary`, model run at `fontWeight: 600` | `caption`, `text.secondary`, line 2 |
| Admin backlog row | `body2`, `text.primary`, model `600` | `caption`, `text.secondary`, line 2 |
| Admin review `h2` | `h5`, same weighting as §7.1 | `h6` span, `text.secondary` |
| Comparison header | `body2`, `600` | `caption`, `text.secondary`, line 2 |
| Tool result list row | `body2` (`ListItemText` primary) | inside `secondary`, first fragment |
| Disambiguation card | `subtitle2` | `Chip size="small" variant="outlined"` |
| Breadcrumb | `body1` inherited, `text.primary` | included, no separate weighting |

The manufacturer is `text.secondary` on every surface where it appears inside
the name run, and is **not** repeated as a separate subtitle anywhere — that
duplication (`CatalogueModelCard.tsx:64`, `CatalogueModelRoute.tsx:200`) goes
away once the manufacturer is part of the name.

---

## 8. Accessibility

1. **Any abbreviated name carries the full one.** Whenever the rendered level
   is below 3, or the text is clamped/ellipsized, the element gets
   `aria-label={formatModelNameA11y(t, parts)}` — the full level-2 form. Where
   the visible text already *is* level 2 and untruncated, no `aria-label` is
   added; a redundant label is noise.
2. **The spoken form differs from the printed form.** `formatModelNameA11y`
   drops the parentheses and spells the range: `BMW R 1300 GS, from 2024`,
   `BMW R 1250 GS, 2019 to 2023`. Screen readers pronounce `–` (en dash)
   inconsistently — some say nothing, which turns `2019–2023` into "twenty
   nineteen twenty twenty-three".
3. **Tooltip semantics.** `<Tooltip title={fullForm} describeChild>` wrapping an
   element that already carries `aria-label={fullForm}`. `describeChild` makes
   the tooltip an `aria-describedby` *description* rather than overriding the
   accessible name, so the name stays stable and the tooltip is not
   double-announced as the name.
4. **A tooltip is never the only carrier.** It is hover-only and therefore
   absent on touch. The full form is always additionally in `aria-label`, and
   on mobile §4.2 chooses wrapping over truncation precisely so nothing depends
   on hover.
5. **Type-code chips** get `aria-label={t("admin.identity.typeCodeA11y", {code})}`
   → `Type code K81`, so the bare token is not read as a word. A truncated list
   (`+2`) gets `aria-label={t("admin.identity.typeCodesMore", { codes })}`
   naming the hidden codes, so nothing is hover-only.
6. **Image `alt`** uses the a11y form (rule 2), not the printed form —
   `CatalogueModelCard.tsx:98`, `RecommendationCard.tsx:103`,
   `ModelImageGallery.tsx:71`, `ModelImagePanel.tsx:139,150`. The gallery's
   `catalogue.detail.galleryLabel` interpolation gets the same string.
7. **`OperationProgress`** receives an already-rendered level-1 string for its
   `admin.backlog.progressLabel`; it does no formatting itself, which keeps its
   single-`progressbar` semantic intact.
8. **Disambiguation cards** are `CardActionArea` buttons in a `role="group"`
   with `aria-label={t("consultations.tools.disambiguate.groupLabel")}`; each
   card's accessible name is the level-2 a11y form plus the power line, so
   choosing by ear is possible.
9. **The `h1` runs are one accessible string.** Splitting the name into
   `<span>`s must not split it for a screen reader — no `aria-hidden` on any
   run, no interleaved punctuation elements; whitespace between runs is real
   whitespace.

---

## 9. i18n keys

New keys, in the existing namespaces. Manufacturer, buildingline, model and
trim strings are **exempt** and rendered verbatim (the standing exemption
for server-generated display content).

| Key | Example value |
|---|---|
| `common.modelName.yearRange` | `{{from}}–{{to}}` |
| `common.modelName.yearFrom` | `from {{from}}` |
| `common.modelName.yearUntil` | `until {{to}}` |
| `common.modelName.yearSingle` | `{{year}}` |
| `common.modelName.a11yYearRange` | `{{from}} to {{to}}` |
| `common.modelName.a11yYearFrom` | `from {{from}}` |
| `common.modelName.qualifierJoin` | `{{range}}, {{qualifier}}` |
| `consultations.tools.disambiguate.title` | `Which one did you mean?` |
| `consultations.tools.disambiguate.groupLabel` | `Model options` |
| `consultations.tools.disambiguate.noCandidates` | `No matching models found.` |
| `consultations.tools.disambiguate.none` | `None of these` |
| `consultations.tools.disambiguate.browseAll` | `Browse all {{count}} models` |
| `catalogue.search.aliasNotice` | `Showing results for {{resolved}}` — only if the backend ever reports a rewrite (§2.2) |
| `catalogue.search.noMatch` | `No model matches "{{query}}". Try "{{suggestion}}".` |
| `admin.review.tabs.identity` | `Identity` |
| `admin.identity.*` | manufacturer / buildingline / modelName / yearFrom / yearTo / typeCodes labels + hints |
| `admin.identity.typeCodeA11y` | `Type code {{code}}` |
| `admin.identity.typeCodesMore` | `and {{count}} more: {{codes}}` |
| `admin.identity.typeCodesHint` | `Used to find and look up this model. Never shown to customers.` |
| `admin.identity.variants.*` | `Trims` heading, base hint, add, remove, name, description, delta-spec add/remove |
| `catalogue.detail.trims.*` | chip-row heading, per-trim delta line |
| `admin.identity.preview.*` | `Preview`, `Level {{n}}` |
| `admin.backlog.sameName` | `{{count}} generations` |

---

## 10. What this contract cannot reach

Stated so it is not mistaken for an oversight:

- **Assistant prose.** The LLM writes names inside its markdown answer. There
  is no safe way to re-render those client-side (a regex over model output that
  rewrites names would corrupt quotes and product prose, and could be steered
  by injected content). The mitigation is upstream: every tool payload handed to
  the agent must contain the **level-2 name** for each bike, so the model has a
  correct form to copy. That is a backend/prompt requirement, flagged here, not
  changed here.
- **Server-composed tool strings** — `licence_fit_check`'s `rule.label` and
  `evidence`, `cost_estimator`'s `item.label`, `OperationProgress`'s `message`.
  These are rendered verbatim by pinned convention. Whoever composes them
  server-side must compose at level 2.
- **Retrieved source titles and heading paths** (`MessageSources`,
  `ModelDocumentsPanel`). These are third-party content; they say whatever the
  source page said, and re-rendering them would misrepresent the source. They
  stay verbatim, always.
- **User-typed text** — chat titles, the `flag_unknown_bike` quote, the
  add-model dialog input, a future search box. Echoed exactly as typed.

---

## 11. Degradation while the schema lands

The schema work is concurrent. Until the §1.1 fields ship, `formatModelName`
can be introduced against today's payload with `modelName ?? name` as the model
part, `manufacturer` as the manufacturer part, `yearFrom`/`yearTo` present, and
`buildingline`, `typeCodes`, `variants`, `displayLevel` all absent. The clamp
rules (§1.2) then produce level 1 or 2 output automatically, which is no worse
than today's `AdminBacklogRoute.displayName()` and removes the local pre-built
string. Every call site can therefore migrate before the schema does, and gains
the new parts without further edits.

---

## 12. Open questions for the owner

| # | Question | Recommended default |
|---|---|---|
| Q1 | Does every bike-bearing payload carry `displayLevel`, computed per result set? | **Yes.** Without it the client cannot know the set, and level choice degrades to a guess. It is one small integer per row. |
| Q2 | ~~Base trim: omit, or render the word `Base`?~~ | **Closed by D2.** No name carries a trim, so there is no base suffix to omit; the admin panel states "this row is the base" above the trim list instead. |
| Q3 | Is `yearTo === null` sufficient for "still in production", or is a separate `inProduction` flag wanted? | **`yearTo === null` is sufficient.** A second field that can disagree with the first is a bug waiting to be filed. |
| Q4 | Is `nameQualifier` (`Euro 5+`) a real column? | **Optional.** Render it inside the year-range parentheses when present; if the architect does not model it, drop it — no surface depends on it. |
| Q5 | ~~Are aliases admin-editable, or ingestion-only?~~ | **Moot (D3)** — nothing stores aliases. If the metadata column is ever added the answer stands: admin-editable, ingestion entries marked and deletable. |
| Q6 | Should the catalogue URL become the stable slug (`bmw/r-1300-gs/2023-`) instead of the ULID? | **No.** Keep `/catalogue/:motorbikeId` (Phase-4 pinned; recommendation cards already carry the ULID). Add the slug later as a redirect-only alias if SEO ever matters. The slug no longer contains a type code (D5), so that objection is gone; the ULID one stands. |
| Q7 | Disambiguation: a new tool, or a flag on `catalogue_search`? | **A flag** (`ambiguous: true` + `candidates[]`). No new tool, no agent-loop change, one new dispatch branch in `ToolResultBlock`. |
| Q8 | Are trim names translated? | **No** — verbatim, same exemption as model and manufacturer names. `Adventure` is a product name, not an English word here. |
| Q9 | Do trims have a meaningful order? | **Yes, the stored array order.** The base is not in the array. Editing order via up/down `IconButton`s only if the owner confirms order matters; otherwise append-only. |
| **Q11** | The trim `description` is free text written by extraction or an admin and shown to customers (§6.5). English only, or a translation surface? | **English only, verbatim** — like a source title. Making it translatable means translating catalogue content, which nothing else in this app does. |
| ~~Q12~~ | ~~Show a trim's delta specs to customers, or keep them admin-only until trim-aware filtering exists?~~ | **Closed by the owner: show them** (§6.5), labelled as differences from the base. The filter gap (D4) stays a backend concern — never phrase a trim line so it reads like a filter promise. |
| Q10 | Should the customer ever see a type code — e.g. on a "parts and compatibility" surface? | **Not in this product.** The doc allows it for workshop/parts questions; we have no such surface, so `typeCodes` stays out of customer payloads entirely (§1.1). Revisit only if a parts feature is specced. |
