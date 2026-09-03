# Phase 4 — UI Specification: Customer catalogue

**Binding for the Phase-4 frontend steps (4.7, 4.8, 4.9)** — reconciled with
the architect by the PM, 2026-08-28; the former open points are resolved in
§12. Where this spec and [`shared-knowledge.md`](shared-knowledge.md)
disagree, shared-knowledge wins — report the conflict, don't build either
version.

Produced by the ui-ux-designer (step 4.6, executed at slicing time) for the
catalogue list + model detail + recommendation-card link. Read
[`../phase-1/shared-knowledge.md`](../phase-1/shared-knowledge.md) and
[`../phase-2/shared-knowledge.md`](../phase-2/shared-knowledge.md) "Frontend
conventions" + "Landed decisions" first, and the Phase-3
[`../phase-3/ui-spec.md`](../phase-3/ui-spec.md) whose shared conventions this
spec extends.

Shared conventions for every spec below (Phase-1/2/3 conventions continue to
apply; deltas are marked):

- MUI v6/v7, Material Design 2 look, stock components only; palette tokens
  only, never hardcoded colors. Icons are Material Symbols via
  `<Icon>glyph_name</Icon>` — **never** `@mui/icons-material`.
- All strings via react-i18next `t()` — full key list in §9. **Deliberate
  exemptions** (server-generated display content, rendered verbatim, same rule
  as Phases 2/3): model names, manufacturer names, prose-section markdown,
  source titles, image attribution strings. Spec **enum values** (category,
  price band) are the one delta: on this customer surface they render through
  the hoisted `common.specEnums.*` labels (§2.1) with verbatim fallback — a
  raw `sport_touring` is admin-speak, not customer-speak.
- Markdown: `react-markdown` + `remark-gfm`, **raw HTML off** (never add
  `rehype-raw`), links rendered as external MUI `Link`s
  (`target="_blank" rel="noopener noreferrer"`) — exactly the Phase-2 §7
  configuration. Prose sections are retrieved web content; they stay inert.
- Data via TanStack Query over the typed `openapi-fetch` client. **No
  optimistic updates** — this phase has no customer mutations at all.
- Forms: filter controls are plain controlled/uncontrolled MUI inputs. No
  RHF/Zod anywhere in this phase.
- Dates/times: not rendered on these screens (no delta).
- Search-param writes use `setSearchParams(..., { replace: true })` (Phase-2
  pinned convention: filters are view state; the back button must leave the
  page, not unwind filter clicks).
- No new dependencies.
- **Wire names are frozen in `shared-knowledge.md`** (the `catalogue-models`
  resource tables). This spec pins the **SPA-side URL search params** (§3.2 —
  a UX contract: short, shareable URLs). The data-hook layer owns the one
  mapping SPA param → wire param (`ccMin/ccMax` → `filter[engineCcMin/Max]`,
  `kwMin/kwMax` → `filter[powerKwMin/Max]`, `seatMax` →
  `filter[seatHeightMmMax]`, `weightMax` → `filter[wetWeightKgMax]`, `a2=1` →
  `filter[a2Eligible]=true`, `category`/`priceBand`/`manufacturer` →
  `filter[…]` same names, `sort` `price|-price` → `msrpEur|-msrpEur`,
  `page` → `page[number]` with `page[size]=24`); renderers never see wire
  names.

---

## 1. Route & file map

Routes (React Router v7, package `react-router`; extends the pinned table —
the whole subtree sits under `RequireAuth`, so a deep link into a detail page
from a fresh session redirects through login and back via the existing
`navigate(from)` flow):

```tsx
<Route element={<RequireAuth />}>
  {/* index → /consultations, consultations subtree, admin subtree unchanged */}
  <Route path="catalogue">
    <Route index element={<CatalogueRoute />} />
    <Route path=":motorbikeId" element={<CatalogueModelRoute />} />
  </Route>
</Route>
```

**Decision — path param name:** `:motorbikeId` (ULID), matching the href
contract reserved in Phase-3 ui-spec §9 (`/catalogue/${motorbikeId}`). The
step-4.2 outline's `:productId` wording is superseded by the reserved
contract. ULID, not slug (step-4.2 risk note: ULID is the simpler choice and
recommendation cards already carry `motorbikeId`).

| Concern | In the URL | Not in the URL |
|---|---|---|
| Which model (detail) | `/catalogue/:motorbikeId` path param | — |
| Every list filter, sort, page | Search params (§3.2) — **single source of truth**, reload/share reproduces the view | — |
| Filter-drawer open state (mobile) | — | local `useState` |
| Selected gallery image (detail) | — | local `useState` |
| In-flight text of a number filter field being typed | — | uncontrolled input buffer, committed on blur/Enter (§3.4) |

**Files** (landed convention: route components in `frontend/src/routes/` with
the `*Route.tsx` suffix — the step-4.2 outline's `CatalogueListPage.tsx` /
`ModelDetailPage.tsx` names are overruled; shared components **flat** in
`frontend/src/components/`, hooks in `frontend/src/hooks/`):

| File | Content |
|---|---|
| `frontend/src/routes/CatalogueRoute.tsx` | §3 list: toolbar, filter surfaces, card grid, pagination, states. |
| `frontend/src/routes/CatalogueModelRoute.tsx` | §4 detail: header, gallery, spec table, prose, sources, states. |
| `frontend/src/components/CatalogueFilters.tsx` | §3.4 — the filter control stack, rendered in the sidebar (desktop) and the drawer (mobile). |
| `frontend/src/components/CatalogueModelCard.tsx` | §3.5 card anatomy. |
| `frontend/src/components/ModelSpecTable.tsx` | §4.3 grouped verified-spec table. |
| `frontend/src/components/ModelImageGallery.tsx` | §4.2. |
| `frontend/src/components/ModelSources.tsx` | §4.5 — the out-of-chat provenance surface (grading-critical). |
| `frontend/src/hooks/useCatalogueFilters.ts` | §3.3 — `useCatalogueFilters()`: parse/normalize search params, write helpers, active-filter count. Pure parsing exported as `parseCatalogueFilters(params)` for tests. Never a stub (pure URL logic, step 4.7). |
| `frontend/src/hooks/useCatalogueModels.ts` | `useCatalogueModels(filters)`, `useManufacturers()` + types `CatalogueListItem`, `Manufacturer`. **Stub in 4.7, made real (deleted wholesale) in 4.9.** |
| `frontend/src/hooks/useCatalogueModel.ts` | `useCatalogueModel(motorbikeId)` + types `CatalogueModelDetail`, `CatalogueImage`, `ModelSource`, `CatalogueError` (`status` + `code`, `ProductError` shape). **Stub in 4.8, made real (deleted wholesale) in 4.9.** |
| `frontend/src/components/RecommendationCard.tsx` | **Modified** per §6 (step 4.9) — the only Phase-3 component the card link touches. |
| `frontend/src/components/specFields.ts` | **Extended** with `formatSpecEnum` (§2.1); existing exports untouched. |

Presentational components (`CatalogueModelCard`, `ModelSpecTable`,
`ModelImageGallery`, `ModelSources`) receive already-fetched data as props and
translate their own chrome strings; they never call the `useCatalogue` hooks
themselves (Phase-3 rule — keeps fixtures/tests trivial).

**Query keys** — extend `frontend/src/queryKeys.ts` with builders (never
hand-typed arrays):

| Key | Query |
|---|---|
| `["catalogue", "list", normalizedFilters]` | customer list endpoint (approved-only server-side; wire name per shared-knowledge). `normalizedFilters` is the §3.3 parsed object — arrays sorted, absent params omitted — so the key is stable per URL state. |
| `["catalogue", "detail", motorbikeId]` | customer detail endpoint |
| `["manufacturers", "list"]` | manufacturer options for the filter select (`staleTime: 5 * 60_000` — near-static) |

Deliberately a **separate `["catalogue", …]` namespace** from the admin
`["products", …]` keys: different endpoint shape, different visibility rules,
and admin invalidation traffic must not churn customer screens (and vice
versa). §7 wires one SSE mapping between them.

`useCatalogueModels` uses `placeholderData: keepPreviousData` — filter and
page changes keep the previous grid on screen while the refetch runs (§3.7
shows the progress bar). No page-walking: this list is genuinely paginated in
the UI (unlike the Phase-2/3 walk-all-pages hooks).

---

## 2. Shared building blocks

### 2.1 Spec display helpers (reuse + one extension)

All spec labels/units/values on both screens go through the existing
`frontend/src/components/specFields.ts` helpers — `specFieldLabel(t, field)`
(keys `consultations.specFields.*`), `specFieldUnit(t, field)`
(`consultations.specUnits.*`) and `formatSpecValue(t, value)`. **No new spec
labels are invented anywhere in this phase.**

One extension in the same file:

```ts
/** Customer-facing label for a category/priceBand enum value; unknown values render verbatim. */
export function formatSpecEnum(t: TFunction, field: "category" | "priceBand", value: string): string
```

backed by **hoisted i18n blocks** `common.specEnums.category.*` and
`common.specEnums.priceBand.*`. The strings move verbatim from
`admin.review.specs.categoryValues.*` / `priceBandValues.*`, which are
**deleted**; `ModelSpecsPanel` (admin) is updated to read the new keys —
identical rendering, same hoist precedent as Phase-3's `admin.live` →
`common.live`. In chat surfaces enum values keep rendering verbatim
(Phase-3 rule unchanged); `formatSpecEnum` is used only by §3.5, §4.1 and
§4.3.

### 2.2 Reused as-is

- `EmptyState` (Phase-2 §2.2) for every empty/error surface below.
- The Phase-3 no-image fallback pattern: a fixed-height
  `<Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", bgcolor: "action.hover" }}>`
  with `<Icon sx={{ color: "text.secondary" }}>two_wheeler</Icon>` — heights
  per surface (§3.5, §4.2).
- The Phase-2 skeleton conventions (per-surface `Skeleton`s sized like the
  real content — no layout jump, no page overlay).
- `LiveConnectionAlert` is **not** rendered on catalogue screens — a static
  read-only catalogue degrades gracefully; the alert would be noise (same
  reasoning as the Phase-3 consultation list).

---

## 3. CatalogueRoute — `/catalogue`

### 3.1 Layout

Desktop (`md`+ — inside `AppLayout`'s `lg` Container):

```
Catalogue (h4)
┌ Grid container spacing={3} ─────────────────────────────────────────┐
│ ┌ Filters (md=3) ──────┐  ┌ Results (md=9) ───────────────────────┐ │
│ │ Paper outlined, p:2  │  │ 42 models      [ Sort by: Name A–Z ▾] │ │
│ │  Category        ▾   │  │ [———— LinearProgress while fetching ] │ │
│ │  Price band      ▾   │  │ ┌────┐ ┌────┐ ┌────┐                  │ │
│ │  Manufacturer    ▾   │  │ │card│ │card│ │card│                  │ │
│ │  Engine (cc) [min|max│  │ └────┘ └────┘ └────┘                  │ │
│ │  Power (kW)  [min|max│  │ ┌────┐ ┌────┐ ┌────┐                  │ │
│ │  Max seat height [  ]│  │ │card│ │card│ │card│                  │ │
│ │  Max weight      [  ]│  │ └────┘ └────┘ └────┘                  │ │
│ │  ☐ A2-eligible only  │  │          ‹ 1 2 3 ›                    │ │
│ │  [ CLEAR FILTERS ]   │  └───────────────────────────────────────┘ │
│ └──────────────────────┘                                            │
└─────────────────────────────────────────────────────────────────────┘
```

Mobile (`< md`): the sidebar disappears; the toolbar row above the grid holds
the result count, the sort select and a **Filters button** opening a `Drawer`
(§3.6). Cards stack 1–2 per row.

- Page header: `<Typography variant="h4" component="h1" sx={{ mb: 2 }}>`
  `catalogue.list.title`.
- Shell: `<Grid container spacing={3}>` — filter pane
  `size={{ md: 3 }}` `sx={{ display: { xs: "none", md: "block" } }}` wrapping
  `<Paper variant="outlined" sx={{ p: 2 }}>` with `CatalogueFilters`; results
  pane `size={{ xs: 12, md: 9 }}`.
- Results toolbar:
  `<Stack direction="row" spacing={2} sx={{ mb: 1, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>`:
  - `<Typography variant="body2" color="text.secondary">`
    `t("catalogue.list.resultCount", { count })` from `meta.totalCount`
    (i18next plural keys; renders a `Skeleton width={80}` inline while no data
    yet).
  - Right group (`<Stack direction="row" spacing={1}>`): the sort select
    (§3.4 #9 — lives in the toolbar on **both** breakpoints, never in the
    drawer) and, `< md` only, the Filters button (§3.6).
- Progress slot: `<Box sx={{ height: 4, mb: 2 }}>` **always rendered**;
  while `isFetching` it contains `<LinearProgress aria-label={t("catalogue.list.loadingLabel")} />`
  — refetches show progress (graded surface) without any layout jump.
- Grid: `<Grid container spacing={2} aria-busy={isFetching}
  aria-label={t("catalogue.list.gridLabel")}>`, one card (§3.5) per item at
  `size={{ xs: 12, sm: 6, md: 4, lg: 3 }}`.
- Pagination: `<Stack alignItems="center" sx={{ mt: 3 }}>` wrapping
  `<Pagination count={pageCount} page={page} shape="rounded"
  onChange={…} />` (MUI supplies the nav semantics and per-page
  `aria-label`s). Rendered only when `pageCount > 1`. `pageCount =
  Math.ceil(totalCount / PAGE_SIZE)`; **`PAGE_SIZE = 24`** is a frontend
  constant mirroring the backend page size (reconciliation point R3). On page
  change: write the `page` param (replace), then
  `window.scrollTo({ top: 0 })` — a new page starting mid-scroll is
  disorienting. Filter changes do **not** scroll.

### 3.2 URL search params (the shareable-view contract — binding)

Every filter, the sort and the page live in React Router search params via
`useSearchParams`; there is **no duplicated filter state** anywhere. Params
(SPA-side names — the hook maps them to wire names per shared-knowledge):

| Concept | Param | Format | Absent means |
|---|---|---|---|
| Categories (multi) | `category` | comma-separated `SpecCategory` values, e.g. `naked,sport` | no category filter |
| Price bands (multi) | `priceBand` | comma-separated band values | no band filter |
| Manufacturer | `manufacturer` | single manufacturer ULID (resolved R2; the SPA treats it as opaque) | all manufacturers |
| Engine displacement | `ccMin`, `ccMax` | positive integer (cc) | unbounded |
| Power | `kwMin`, `kwMax` | positive number (kW) | unbounded |
| Seat height ceiling | `seatMax` | positive integer (mm) | unbounded |
| Weight ceiling | `weightMax` | positive number (kg) | unbounded |
| A2-eligible only | `a2` | literal `1` | off |
| Sort | `sort` | `name` \| `-name` \| `price` \| `-price` | `name` |
| Page | `page` | integer ≥ 2 | page 1 |

Normalization rules (in `parseCatalogueFilters`, applied on read — the URL is
never rewritten to "clean" it):

- Unknown enum members inside `category`/`priceBand` are dropped; an empty
  result drops the whole filter.
- Non-numeric / non-positive numeric params are treated as absent.
- Unknown `sort` values → default `name`. `page` not a positive integer → 1.
- Defaults are **omitted** when writing (page 1 and sort `name` never appear
  in the URL — one canonical URL per view).
- `min > max` on a pair is **not** client-corrected: both params are kept and
  sent; the (empty) result renders the §3.7 no-match state. No cross-field
  validation UI.

### 3.3 `useCatalogueFilters()`

Returns `{ filters, setFilter, clearFilters, activeFilterCount }`:

- `filters`: the normalized object (arrays sorted alphabetically so the query
  key is order-independent).
- `setFilter(patch)`: merges, drops now-absent/default keys, **always deletes
  `page`** (any filter or sort change resets to page 1), writes with
  `{ replace: true }`.
- `clearFilters()`: removes all eight filter concepts **and** `page`; keeps
  `sort` (a sort preference is not a filter).
- `activeFilterCount`: how many of the eight filter concepts have ≥ 1 value
  (a min/max pair counts once) — drives the mobile badge (§3.6) and the
  no-match vs empty-catalogue branch (§3.7).

### 3.4 `CatalogueFilters` — controls & apply behaviour

One component, rendered in the desktop sidebar and inside the mobile drawer.
`<Stack spacing={2} component="fieldset" sx={{ border: 0, m: 0, p: 0 }}>`
with a visually-hidden legend `catalogue.filters.title`. Controls top to
bottom (all `size="small"`, `fullWidth`):

1. **Category** — `<TextField select>` with
   `slotProps={{ select: { multiple: true, renderValue } }}`; one `MenuItem`
   per pinned `SpecCategory` value containing `<Checkbox size="small">` +
   `<ListItemText>` with `formatSpecEnum(t, "category", value)`;
   `renderValue` joins the same labels with ", ". Label
   `catalogue.filters.category`.
2. **Price band** — identical pattern, values from the pinned band
   vocabulary, labels via `formatSpecEnum(t, "priceBand", value)`. Label
   `catalogue.filters.priceBand`.
3. **Manufacturer** — single `<TextField select>`; first
   `MenuItem value=""` `catalogue.filters.manufacturerAll`, then one per
   manufacturer from `useManufacturers()` (name verbatim, sorted by name).
   While the manufacturers query loads or errors, the control renders
   `disabled` (options unavailable; the other filters keep working — no error
   surface for this non-critical lookup, it recovers on the next mount).
4. **Engine displacement** — a labelled pair:
   `<Typography variant="caption" color="text.secondary">`
   `catalogue.filters.engineCc`, then
   `<Stack direction="row" spacing={1}>` of two number fields (§ number-field
   pattern below) with labels `catalogue.filters.min` / `catalogue.filters.max`.
5. **Power** — same pair pattern, caption `catalogue.filters.powerKw`.
6. **Max seat height** — single number field, label
   `catalogue.filters.seatHeightMax`.
7. **Max weight** — single number field, label
   `catalogue.filters.weightMax`.
8. **A2-eligible only** — `<FormControlLabel control={<Checkbox />}
   label={t("catalogue.filters.a2Only")} />`.
9. **Sort** (toolbar, not in this stack — listed here for completeness):
   `<TextField select size="small" sx={{ minWidth: 190 }}
   label={t("catalogue.sort.label")}>` with four options —
   `catalogue.sort.nameAsc|nameDesc|priceAsc|priceDesc` mapping to
   `name|-name|price|-price`.
10. **Clear** — `<Button variant="text" startIcon={<Icon>filter_alt_off</Icon>}
    disabled={activeFilterCount === 0}>` `catalogue.list.clearFilters` →
    `clearFilters()`.

**Apply behaviour (decision — no Apply button):**

- Selects and the checkbox **apply immediately** on change (one discrete
  intent = one refetch; `keepPreviousData` + the progress bar make this
  cheap).
- Number fields **commit on blur and on Enter** (Enter `preventDefault()`s),
  not per keystroke — no debounce timer, no keystroke-level URL churn, no
  duplicated live state. Pattern: **uncontrolled** `TextField
  type="number"` with `defaultValue={filters.ccMin ?? ""}` and
  `key={String(filters.ccMin ?? "")}`, `slotProps={{ htmlInput: { min: 0,
  inputMode: "numeric" } }}` — the `key` remounts the field whenever the URL
  value changes externally (clear filters, back button), so the URL remains
  the single source of truth between edits. An empty or invalid commit
  removes the param.

### 3.5 `CatalogueModelCard`

Props: one `CatalogueListItem`. `<Card variant="outlined">` whose **entire
surface** is `<CardActionArea component={RouterLink}
to={`/catalogue/${motorbikeId}`}>` (real href — middle-click works):

1. Image: `<CardMedia component="img" height={160} image={cardUrl}
   srcSet={`${thumbUrl} 320w, ${cardUrl} 640w`}
   sizes="(max-width: 600px) 100vw, 280px" alt={name} loading="lazy"
   sx={{ objectFit: "cover" }} />`. **No image** (models can be approved
   without one): the §2.2 fallback Box at `height: 160` with a 48px icon —
   card height stays stable.
2. `<CardContent>`:
   - `<Typography variant="subtitle1" component="h2" noWrap>` — model name
     verbatim.
   - `<Typography variant="body2" color="text.secondary" noWrap>` —
     manufacturer name verbatim; when category is present, ` · ` +
     `formatSpecEnum(t, "category", category)`.
   - When `priceBand` present:
     `<Chip size="small" variant="outlined" sx={{ mt: 1 }}
     label={formatSpecEnum(t, "priceBand", priceBand)} />`.
   - Headline specs: up to four
     `<Typography variant="caption" color="text.secondary" display="block">`
     lines in the fixed order **engineCc, powerKw, wetWeightKg,
     seatHeightMm**, each
     `{specFieldLabel(t, field)}: {formatSpecValue(t, value)} {specFieldUnit(t, field)}`
     — **render only non-null values; a null line is omitted, never dashed,
     never guessed** (card context: unknowns are noise; the detail table is
     the completeness surface).

**Data needs (list item):** motorbikeId, name, manufacturer name (nullable),
category (nullable), priceBand (nullable), image variant URLs
(`thumb`/`card`, nullable — `/media/motorbikes/{motorbikeId}/{imageId}_{variant}.webp`),
headline specs engineCc/powerKw/wetWeightKg/seatHeightMm (all nullable).
Slim summary payload — no prose, no sources, no full spec object (step-4.2
risk note; wire shape per shared-knowledge, R3).

### 3.6 Mobile filter drawer (decision: temporary Drawer, right anchor)

Below `md` the sidebar is hidden and the toolbar gains:

```tsx
<Badge badgeContent={activeFilterCount} color="primary">
  <Button variant="outlined" size="small" startIcon={<Icon>filter_list</Icon>}
          onClick={openDrawer}>{t("catalogue.filters.open")}</Button>
</Badge>
```

`<Drawer anchor="right" open={open} onClose={close}>` with a
`<Box sx={{ width: 300, p: 2 }} role="dialog"
aria-label={t("catalogue.filters.title")}>`:

- Header row: `<Typography variant="h6" component="h2">`
  `catalogue.filters.title` + `<IconButton edge="end"
  aria-label={t("catalogue.filters.close")}><Icon>close</Icon></IconButton>`.
- The same `CatalogueFilters` stack (filters apply immediately to the URL
  behind the drawer — same semantics as desktop, no separate staged state).
- Sticky footer: `<Button fullWidth variant="contained" sx={{ mt: 2 }}>`
  `t("catalogue.filters.showResults", { count: totalCount })` — closes the
  drawer (count live-updates as filters change, which is the payoff of
  apply-on-change; while fetching it renders `common.loading` as the label).

Drawer open state is local `useState`. Not a `SwipeableDrawer` (no new
interaction patterns needed); rendered conditionally on
`useMediaQuery(theme.breakpoints.down("md"))` so desktop never mounts it.

### 3.7 States

| State | Rendering |
|---|---|
| Loading (`isLoading`, no cached data) | Header + filter pane render fully (static enum options; manufacturer select disabled while its query loads); result count shows an inline `Skeleton width={80}`; grid renders **8 skeleton cards**: `<Card variant="outlined">` with `<Skeleton variant="rectangular" height={160} />` + two text `Skeleton`s in a `CardContent` — same dimensions as real cards, zero layout jump. No pagination. |
| Refetch after filter/sort/page change | Previous grid stays (`keepPreviousData`); the reserved progress slot shows `LinearProgress`; grid `aria-busy`. Nothing else flashes. |
| Error (list query) | Toolbar + `EmptyState` in place of the grid: icon `error`, `catalogue.list.loadError` title, `common.errors.serverError` body, action `<Button onClick={refetch}>` `common.retry`. Filter pane stays usable. |
| Empty catalogue (`totalCount === 0` **and** `activeFilterCount === 0`) | `EmptyState`: icon `two_wheeler`, `catalogue.list.emptyTitle` / `emptyBody`, action `<Button variant="contained" component={RouterLink} to="/consultations">` `catalogue.list.emptyAction` (the advisor is how models get flagged and added — no dead "add" affordance for customers). |
| No filter match (`totalCount === 0`, filters active) | `EmptyState`: icon `filter_alt_off`, `catalogue.list.noMatchTitle` / `noMatchBody`, action `<Button>` `catalogue.list.clearFilters` → `clearFilters()`. Also covers a shared/stale URL whose `page` exceeds the last page (the server returns an empty page; clearing resets `page`). |
| Live update | `product.updated` SSE (§7) invalidates `["catalogue"]` — a model approved by an admin appears on the next render without reload. Invisible refetch (previous data kept). |

---

## 4. CatalogueModelRoute — `/catalogue/:motorbikeId`

### 4.1 Layout & header

```
Catalogue / Suzuki GSR 600                            ← Breadcrumbs
Suzuki GSR 600 (h4)
Suzuki  [Naked] [Mid (€5,000–10,000)] [A2 eligible]   ← chips row
┌ Grid container spacing={4} ────────────────────────────────┐
│ ┌ Gallery (md=5) ─────────┐ ┌ Verified specs (md=7) ─────┐ │
│ │  [ main image 4:3     ] │ │ Engine & performance       │ │
│ │  [▫][▫][▫] thumbnails   │ │   Engine displacement 599cc│ │
│ │  attribution caption    │ │   Power            72.5 kW │ │
│ └─────────────────────────┘ │ Dimensions & ergonomics …  │ │
│                             └────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
About this bike (h5)                        ← prose sections
  markdown…
Sources (h5, Paper outlined)                ← §4.5
  ▪ Suzuki GSR600 — Wikipedia ↗   en.wikipedia.org
```

- `<Breadcrumbs sx={{ mb: 2 }}>`: `<Link component={RouterLink}
  to="/catalogue">` `catalogue.detail.back` + `<Typography
  color="text.primary" noWrap>` model name. **Plain `/catalogue`** — the
  browser back button restores any filtered view; the breadcrumb is the
  canonical entry, not a state-preserving return (filters live in the list
  URL, and arriving from a recommendation card there is no filter state to
  restore).
- Title: `<Typography variant="h4" component="h1">` name verbatim; beneath
  it `<Stack direction="row" spacing={1} sx={{ mt: 1, mb: 3, alignItems:
  "center", flexWrap: "wrap" }}>`:
  - `<Typography variant="subtitle1" color="text.secondary">` manufacturer
    name verbatim (omit when null);
  - `<Chip size="small" label={formatSpecEnum(t, "category", category)} />`
    when category present;
  - `<Chip size="small" variant="outlined"
    label={formatSpecEnum(t, "priceBand", priceBand)} />` when present;
  - `<Chip size="small" color="success" variant="outlined"
    label={t("consultations.specFields.a2Eligible")} />` **only when
    `a2Eligible === true`** (null renders nothing — never guess).
- Body: `<Grid container spacing={4}>` — gallery `size={{ xs: 12, md: 5 }}`,
  spec table `size={{ xs: 12, md: 7 }}`; prose (§4.4) and sources (§4.5)
  full-width below.

### 4.2 `ModelImageGallery`

Props: `images` (0..n approved images, each with `thumb`/`card`/`detail`
variant URLs + nullable attribution), `name`. **`CatalogueImage` field
names are the wire keys `thumb`/`card`/`detail`/`attribution`** (matching
the backend `ImageVariants` shape, so 4.9's generated types replace the
4.8 stub without component edits); the `thumbUrl`/`cardUrl`/`detailUrl`
spellings in the sketches below are illustrative only. Local `useState`
for the selected index (0 default; not in the URL). The gallery root
carries `role="group"` +
`aria-label={t("catalogue.detail.galleryLabel", { name })}`.

- Main image: `<Box component="img" src={selected.detailUrl}
  srcSet={`${selected.cardUrl} 640w, ${selected.detailUrl} 1280w`}
  sizes="(max-width: 900px) 100vw, 480px" alt={name}
  sx={{ width: "100%", height: { xs: 240, md: 400 }, objectFit: "contain",
  bgcolor: "action.hover", borderRadius: 1 }} />` — `contain`, not `cover`:
  cropping a motorcycle silhouette destroys the information; the
  `action.hover` letterbox keeps the block visually solid. Fixed heights =
  no layout jump when switching images.
- Thumbnails (**only when `images.length > 1`**): `<Stack direction="row"
  spacing={1} sx={{ mt: 1, overflowX: "auto" }}>` of `<ButtonBase
  aria-label={t("catalogue.detail.imageThumbLabel", { index: i + 1 })}
  aria-pressed={i === selected}>` wrapping a 64×64 `<Box component="img"
  src={thumbUrl} alt="" sx={{ objectFit: "cover", borderRadius: 1,
  border: 2, borderColor: i === selected ? "primary.main" : "transparent" }} />`.
- Attribution: when the selected image carries one,
  `<Typography variant="caption" color="text.secondary" sx={{ mt: 0.5,
  display: "block" }}>` attribution string verbatim (licence compliance —
  must be visible wherever the image is published; availability in the
  customer payload is R5).
- **No images:** the §2.2 fallback Box at the same
  `height: { xs: 240, md: 400 }` with a 64px `two_wheeler` icon — the page
  keeps its shape.
- No lightbox/zoom in this phase (`detail` 1280w in `srcSet` already serves
  the sharpest variant).

### 4.3 `ModelSpecTable` — the 13 fields, grouped (explicit)

Heading above the table: `<Typography variant="h5" component="h2"
sx={{ mb: 1 }}>` `catalogue.detail.specsHeading`.

`<TableContainer component={Paper} variant="outlined">` wrapping
`<Table size="small" aria-label={t("catalogue.detail.specsTableLabel")}>`.
Group header rows: `<TableRow>` with a single
`<TableCell colSpan={2} sx={{ bgcolor: "action.hover" }}>` containing
`<Typography variant="subtitle2">` the group label. Field rows: label cell
`<TableCell component="th" scope="row" sx={{ width: "55%" }}>`
`specFieldLabel(t, field)` + value cell
`{formatSpecValue(t, value)} {specFieldUnit(t, field)}` (`category` and
`priceBand` values via `formatSpecEnum`; booleans render `common.yes`/`no`
via `formatSpecValue`).

**Binding group → field mapping** (all 13 frozen keys, table order within
groups):

| Group (i18n key) | Fields |
|---|---|
| `catalogue.detail.groups.engine` — "Engine & performance" | `engineCc`, `cylinders`, `powerKw`, `torqueNm`, `topSpeedKmh` |
| `catalogue.detail.groups.chassis` — "Dimensions & ergonomics" | `wetWeightKg`, `seatHeightMm`, `tankCapacityL` |
| `catalogue.detail.groups.safety` — "Licence & safety" | `abs`, `a2Eligible` |
| `catalogue.detail.groups.market` — "Classification & price" | `category`, `priceBand`, `msrpEur` |

`msrpEur` is the one field not rendered via `formatSpecValue`: format with
`new Intl.NumberFormat(i18n.language, { style: "currency", currency: "EUR",
maximumFractionDigits: 0 })` (project-wide EUR pin; no separate unit suffix).

**Null handling (decision — omission, not em dash):** a null field renders
**no row**; a group whose fields are all null renders **no group header**.
This is a customer sales surface — unknowns are noise here, unlike the §8.3
chat comparison table where columns must stay aligned across bikes (em dashes
stay pinned there). If **all 13 fields are null** (approved without a
verified spec — unusual but legal), the table is replaced by
`<Typography variant="body2" color="text.secondary">`
`catalogue.detail.noSpecs`.

### 4.4 Prose — the article block

Rendered under the Grid when the detail payload carries a non-null `article`
(**resolved R4**: one markdown string — the Wikipedia document's
`content_markdown`; wire shape per shared-knowledge). Block heading
`<Typography variant="h5" component="h2" sx={{ mt: 4, mb: 1 }}>`
`catalogue.detail.aboutHeading`; body via the pinned react-markdown config
(GFM, **raw HTML off**, links as external MUI `Link`s — this is retrieved
web content). The markdown's own `##`/`###` headings render as the prose
sections (map them to `h3`/`h4` typography so the page keeps one `h1` and
ordered levels). `article: null`: the whole block is simply absent — specs +
sources still make a complete page, no empty state.

### 4.5 `ModelSources` (grading-critical — provenance outside the chat)

**Always expanded, never collapsed** — this block is the out-of-chat
"retrieved context/sources are user-visible" requirement; burying it behind
a toggle defeats its purpose.

`<Paper variant="outlined" sx={{ p: 2, mt: 4 }}>`:

1. `<Typography variant="h5" component="h2">` `catalogue.detail.sourcesHeading`.
2. `<Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>`
   `catalogue.detail.sourcesHint` ("Specifications and prose on this page are
   derived from these retrieved documents.").
3. `<List dense disablePadding aria-label={t("catalogue.detail.sourcesLabel")}>`
   — one `ListItem` per source, same row anatomy as Phase-3 §7:
   - `primary`: `<Link href={sourceUrl} target="_blank"
     rel="noopener noreferrer" variant="body2">` source title verbatim + a
     trailing `<Icon fontSize="inherit">open_in_new</Icon>`. A source with
     **no URL** (uploads) renders the title as plain `<Typography
     variant="body2">` with secondary `catalogue.detail.sourceNoUrl` — never
     a dead link.
   - `secondary`: `new URL(sourceUrl).hostname` (URL-less rows: see above).

**Data needs (per source):** title, external URL (nullable). De-duplicate by
URL. Zero sources: the Paper renders with the heading and
`<Typography variant="body2" color="text.secondary">`
`catalogue.detail.sourcesEmpty` — the absence of provenance is itself
information worth showing, not hiding.

### 4.6 States

| State | Rendering |
|---|---|
| Loading (no cached data) | Skeleton page, no layout jump: breadcrumbs with the static `catalogue.detail.back` link + `<Skeleton width={140} />`; `<Skeleton width="40%" height={48} />` title; gallery slot `<Skeleton variant="rounded" sx={{ height: { xs: 240, md: 400 } }} />`; spec pane: 8 `<Skeleton variant="text" />` rows in a `Paper variant="outlined" sx={{ p: 2 }}`. |
| Error — 404 (unknown **or unapproved** id — the backend answers 404 for both, R6; also the target of stale recommendation-card links) | `EmptyState`: icon `search_off`, `catalogue.detail.notFoundTitle` / `notFoundBody`, action `<Button component={RouterLink} to="/catalogue">` `catalogue.detail.back`. |
| Error — network/5xx | `EmptyState`: icon `error`, `catalogue.detail.loadError` title, `common.errors.serverError` body, retry action (`refetch`). |
| Deep link, fresh session | Nothing special to build: the route sits under `RequireAuth`, whose `state={{ from: location }}` + the login flow's `navigate(from)` land the user back on the detail URL after signing in. QA criterion, not new code. |
| No images / all-null specs / no prose / no sources | Per §4.2–§4.5 fallbacks — every combination keeps a complete, stable page. |

**Data needs (detail):** motorbikeId, name, manufacturer name (nullable),
all 13 verified spec fields (nullable), approved images 0..n (variant URLs +
nullable attribution), `article` markdown (nullable), sources 0..n
(title + nullable URL). Full payload belongs to the detail response only.

---

## 5. States matrix (summary)

| Surface | Loading | Empty | No match | Error | 404 | Live |
|---|---|---|---|---|---|---|
| List | 8 skeleton cards + inline count skeleton | `EmptyState two_wheeler` → advisor CTA | `EmptyState filter_alt_off` → clear filters | `EmptyState error` → retry | — | `product.updated` → invisible refetch |
| List refetch | `LinearProgress` in reserved slot, grid kept | — | — | previous data kept; error only when nothing to show | — | — |
| Detail | full-shape skeletons | per-block fallbacks (§4.2–4.5) | — | `EmptyState error` → retry | `EmptyState search_off` → back to catalogue | `product.updated` → invisible refetch |

Progress indicators on these screens: skeletons (initial), `LinearProgress`
(list refetch). No page overlays, no spinners over content.

---

## 6. Recommendation-card link (completes the Phase-3 §9 contract)

`frontend/src/components/RecommendationCard.tsx`: wrap the existing card
content — image/fallback plus `CardContent`, exactly as rendered today — in

```tsx
<CardActionArea component={RouterLink}
                to={`/catalogue/${recommendation.motorbikeId}`}>
```

**and change nothing else** (the Phase-3 ui-spec §9 reserved contract; the
landed component takes a single `recommendation: Recommendation` prop and
the id already rides along as `recommendation.motorbikeId`). No new
strings, no visual changes beyond
MUI's built-in action-area hover/focus feedback. The card in the chat and the
catalogue card (§3.5) remain **separate components** — different data shapes
(rationale line vs price chip), shared only through `specFields.ts`.

---

## 7. App-shell integration

- **Nav (decision — three text buttons, no drawer):** in `AppLayout`, insert
  `<Button color="inherit" component={RouterLink} to="/catalogue">`
  `nav.catalogue` **between** Consultations and Admin — order: Consultations
  (the authenticated home), Catalogue, Admin (admin-only). Three short
  labels still fit a toolbar; a drawer for three destinations is
  over-engineering.
- **Mobile fit:** to make room at `xs`, the AppBar title hides below `sm`:
  `sx={{ …, display: { xs: "none", sm: "block" } }}` plus a
  `<Box sx={{ flexGrow: 1, display: { xs: "block", sm: "none" } }} />`
  spacer so the right-side controls keep their position (precedent: the
  account button already hides the username at `xs`). The current page's
  header identifies the app on phones.
- **No active-state indication** is added to the nav buttons (none exists
  today for Consultations/Admin; consistency over novelty — flag for a later
  polish pass if wanted).
- **SSE:** extend `useServerEvents` — `product.updated` additionally
  invalidates `["catalogue"]` (list + any cached detail; approval/unpublish
  reaches an open customer screen without reload). The reconnect blanket
  invalidation adds `["catalogue"]` too. No new events, no polling.
- Home/index route, login redirect flow, `LiveConnectionAlert` placements:
  unchanged.

---

## 8. Stub fixtures (binding — steps 4.7/4.8 are UI-only)

The PM sliced the frontend UI-first (4.7 list, 4.8 detail, both on stubs;
4.9 wires live at S1 with `make generate-api` as its first action). The two
hook files `useCatalogueModels.ts` (4.7) and `useCatalogueModel.ts` (4.8)
ship the Phase-1/2/3 stub pattern (real `useQuery` results over fixtures,
header comment naming step 4.9 as the one that deletes them wholesale) and
**must exercise every state above**:

- ≥ `PAGE_SIZE + 3` list items (proves real pagination), covering: an item
  with image + all four headline specs; an item with **no image** (fallback
  box); an item with all-null headline specs (name/manufacturer only — no
  stray separators); items spread across categories/bands/manufacturers so
  every filter visibly narrows; the stub filters/sorts/pages the fixture
  array from the parsed URL params (proves reload/share reproduces the view).
- Detail fixtures: one fully-populated model (2 images with attribution —
  proves thumbnails + selection, 13/13 specs, an `article` with two `##`
  sections + one GFM table + an inline `<script>` proving raw HTML stays
  inert, 3 sources incl. one URL-less upload and one duplicate URL to
  prove de-dup); one sparse model (0 images, ~4 non-null specs with one
  all-null group, `article: null`, 1 source); one id answering 404 (proves
  the unapproved/unknown state).
- `useManufacturers` stub: 4 names, one unassigned-manufacturer model in the
  list (renders without the manufacturer line).

---

## 9. i18n keys (merge into `frontend/src/locales/en/translation.json`)

`admin.review.specs.categoryValues` and `…priceBandValues` **move** to
`common.specEnums.category` / `common.specEnums.priceBand` (strings verbatim,
old blocks deleted, admin spec form re-pointed — §2.1). Everything else below
is new. Spec field labels/units are **reused** from
`consultations.specFields.*` / `consultations.specUnits.*` via the
`specFields.ts` helpers — no new spec labels.

```json
{
  "nav": {
    "catalogue": "Catalogue"
  },
  "common": {
    "specEnums": {
      "category": { "…moved verbatim from admin.review.specs.categoryValues…": "" },
      "priceBand": { "…moved verbatim from admin.review.specs.priceBandValues…": "" }
    }
  },
  "catalogue": {
    "list": {
      "title": "Catalogue",
      "gridLabel": "Catalogue models",
      "loadingLabel": "Updating results",
      "resultCount_one": "{{count}} model",
      "resultCount_other": "{{count}} models",
      "loadError": "Could not load the catalogue",
      "emptyTitle": "The catalogue is empty",
      "emptyBody": "No motorcycles have been published yet. Ask the advisor about a model — it gets researched, verified and added here.",
      "emptyAction": "Ask the advisor",
      "noMatchTitle": "No models match these filters",
      "noMatchBody": "Try widening a range or clearing the filters.",
      "clearFilters": "Clear filters"
    },
    "sort": {
      "label": "Sort by",
      "nameAsc": "Name (A–Z)",
      "nameDesc": "Name (Z–A)",
      "priceAsc": "Price (low to high)",
      "priceDesc": "Price (high to low)"
    },
    "filters": {
      "title": "Filters",
      "open": "Filters",
      "close": "Close filters",
      "showResults_one": "Show {{count}} model",
      "showResults_other": "Show {{count}} models",
      "category": "Category",
      "priceBand": "Price band",
      "manufacturer": "Manufacturer",
      "manufacturerAll": "All manufacturers",
      "engineCc": "Engine displacement (cc)",
      "powerKw": "Power (kW)",
      "min": "Min",
      "max": "Max",
      "seatHeightMax": "Max seat height (mm)",
      "weightMax": "Max weight (kg)",
      "a2Only": "A2-eligible only"
    },
    "detail": {
      "back": "Catalogue",
      "notFoundTitle": "Model not found",
      "notFoundBody": "This model does not exist or is not published.",
      "loadError": "Could not load this model",
      "aboutHeading": "About this bike",
      "specsHeading": "Verified specifications",
      "specsTableLabel": "Verified specifications",
      "noSpecs": "No verified specifications are available for this model yet.",
      "groups": {
        "engine": "Engine & performance",
        "chassis": "Dimensions & ergonomics",
        "safety": "Licence & safety",
        "market": "Classification & price"
      },
      "galleryLabel": "Photos of {{name}}",
      "imageThumbLabel": "Show photo {{index}}",
      "sourcesHeading": "Sources",
      "sourcesLabel": "Sources",
      "sourcesHint": "Specifications and prose on this page are derived from these retrieved documents.",
      "sourcesEmpty": "No source documents are recorded for this model.",
      "sourceNoUrl": "Uploaded document"
    }
  }
}
```

(`common.loading`, `common.retry`, `common.yes/no`, `common.errors.serverError`
already exist and are reused. `resultCount`/`showResults` use i18next plural
suffixes.)

---

## 10. Accessibility / UX checklist

- **Progress semantics:** skeletons for initial loads (sized like real
  content — no layout jump); the list-refetch `LinearProgress` carries a
  translated `aria-label` and lives in a permanently reserved slot; grid gets
  `aria-busy` while fetching. No overlays, no focus-stealing.
- **Navigation is real links:** cards are
  `CardActionArea component={RouterLink}` (real hrefs — middle-click and
  copy-link work); breadcrumbs and empty-state actions use `RouterLink`;
  source links are external with `target="_blank" rel="noopener noreferrer"`;
  a URL-less source is plain text, never a dead link.
- **URL is the state:** reload/share/back reproduce every list view; filter
  writes use `replace: true` so back leaves the page; page changes scroll to
  top, filter changes don't.
- **Filter controls:** multi-selects use Checkbox + `ListItemText` menu items
  with a `renderValue` summary; the filter stack is a `fieldset` with a
  visually-hidden legend; the mobile drawer is `role="dialog"` with a
  translated label, a labelled close button, and Escape/backdrop dismissal
  (MUI default); the badge count is supplemented by the same count in the
  drawer's "Show N models" button — never color/badge alone. Number inputs
  set `inputMode: "numeric"` and commit on blur/Enter (IME-safe: Enter commit
  guards `isComposing`).
- **Images:** `loading="lazy"` + `srcSet`/`sizes` everywhere (thumb 320w /
  card 640w on cards; card 640w / detail 1280w on the gallery); `alt` = model
  name; gallery thumbnails are `ButtonBase` with `aria-pressed` and a border
  **plus** the pressed state (not color alone); fallback boxes keep exact
  image dimensions; attribution rendered visibly when present.
- **Tables:** the spec table uses `component="th" scope="row"` label cells
  and a translated `aria-label`; group headers are single-cell rows, not
  visual-only dividers. `TableContainer` + fluid column widths keep it inside
  the viewport at 360px — **no horizontal page scroll anywhere** (cards wrap,
  the gallery thumbnail strip scrolls only within itself).
- **Null discipline:** a null spec renders nothing on cards and no row on the
  detail table (§4.3 decision); enum values unknown to the frontend render
  verbatim (forward compatibility); nothing is ever guessed or defaulted.
- **Headings:** one `h1` per page (list title / model name), `h2` for
  sections (specs, prose sections, sources), `h2` on card titles inside the
  grid — a screen-reader outline that matches the visual hierarchy.

---

## 11. Verification hooks (for the QA agent)

- Set 3+ filters incl. a range and a multi-select → reload → identical
  results and control states; copy the URL into a second session → identical
  view (through the login redirect).
- `page=2`, change any filter → `page` param disappears, page 1 renders.
- An unapproved model's ULID at `/catalogue/:id` → the 404 state, not data.
- A recommendation card in an old chat navigates to the matching detail page.
- Kill the list request (devtools offline) → error state with working retry;
  restore → grid returns.
- 360px viewport: no horizontal page scroll on either screen; drawer filters
  fully operable.

---

## 12. Resolutions (reconciled with the architect by the PM, 2026-08-28)

**R1 — Wire names: resolved.** Frozen in `shared-knowledge.md` (the
`catalogue-models` resource) — JSON:API `filter[…]` params, `sort`
`name|-name|msrpEur|-msrpEur`, `page[number]`/`page[size]`. The SPA params of
§3.2 stand; the data hook owns the one mapping (spelled out in the preamble
bullet). `sort=price/-price` maps to `msrpEur/-msrpEur`.

**R2 — Manufacturer: resolved.** Filter value is the **manufacturer ULID**
(opaque to the SPA; shareable-URL prettiness loses to one-identity
simplicity). `GET /api/manufacturers` relaxes to `current_user` in step 4.4
— exactly the decision Phase 2b reserved for Phase 4; `useManufacturers()`
reads it.

**R3 — List payload & page size: resolved.** Slim summary attributes as
pinned in shared-knowledge (`imageUrl` = card variant; the client derives
the thumb URL via the pinned `_card.webp` → `_thumb.webp` suffix swap).
`PAGE_SIZE = 24` frontend constant, sent as `page[size]=24` (backend
default/max 100 accepts it — no backend pin needed).

**R4 — Prose: resolved.** One nullable `article` markdown string — the
Wikipedia document's `content_markdown` only (scraped marketing pages stay
out; they appear as sources instead). §4.4 rewritten accordingly;
`ProseSection` type dropped.

**R5 — Images: resolved.** The payload is `[{thumb, card, detail,
attribution}]`, approved only, newest first — attribution included
(licensing obligation honoured). n > 1 is legal (repeat ingestions / CLI
image fetches can accumulate approved images), but the current dev DB has
≤ 1 per model — QA proves thumbnails on the 4.8 stub fixtures, the live
check uses whatever the DB holds.

**R6 — 404: confirmed.** Unknown and non-approved ids both answer plain
404 `not-found` on the customer detail endpoint — one not-found state.

**R7 — Price sort: resolved.** Column `msrp_eur`, **NULLS LAST in both
directions**, tiebreak name then id. No `price_band` fallback. Note: no
approved dev model has a verified price yet (open-questions OQ2) — the demo
needs the owner to verify one.

**R8 — SSE: approved.** `product.updated` additionally invalidates
`["catalogue"]`; reconnect blanket gains `["catalogue"]` +
`["manufacturers"]`. Lands in 4.9 with the real hooks (stub data has
nothing to invalidate).

**R9 — i18n hoist: approved.** `admin.review.specs.categoryValues`/
`priceBandValues` move verbatim to `common.specEnums.*`; the admin spec form
is re-pointed (the one admin file this phase touches, frontend-only — the
`admin.live` → `common.live` hoist precedent). Chat surfaces keep rendering
enum values verbatim (Phase-3 rule unchanged). Lands in step 4.7 with
`formatSpecEnum`.
