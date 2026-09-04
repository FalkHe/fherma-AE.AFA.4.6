# Phase 2 — UI Specification (binding for frontend steps)

Produced by the ui-ux-designer; binding for the admin backlog & review UI work
in this phase. Read the phase's step files for the API/data contracts these
screens consume (catalogue domain model, background-job/operations
infrastructure, ingestion pipeline) and
[`../phase-1/shared-knowledge.md`](../phase-1/shared-knowledge.md) for the
landed auth/layout/file conventions this spec builds on.

Shared conventions for every spec below (Phase-1 conventions continue to
apply; deltas are marked):

- MUI v6/v7, Material Design 2 look, stock components only. Theme modes via
  `colorSchemes`; never hardcode colors — palette tokens only
  (`text.secondary`, `error`, `divider`, …). Icons are Material Symbols via
  `<Icon>glyph_name</Icon>` (the `MuiIcon` default prop in `theme.ts` sets the
  font class), same as `ThemeModeToggle`.
- All strings via react-i18next `t()` — full key list in §10, including
  `aria-label`s. **One deliberate exemption:** operation `message`
  values and failed-operation error text are server-generated display content
  (like document prose) and render verbatim, not through `t()`.
- Forms: plain controlled inputs everywhere **except** the draft-spec review
  form (§8), which is the first form that outgrows login and therefore uses
  **React Hook Form + Zod** (`@hookform/resolvers`) as permitted by
  `docs/general/frontend-stack.md`. Nothing else in this phase may adopt RHF/Zod.
- Data via TanStack Query over the typed `openapi-fetch` client (regenerated
  from the backend schema before implementation). Query keys pinned in §1.
- **No optimistic updates anywhere in the admin UI.** Status transitions are
  validated server-side; every mutation awaits the server, then invalidates —
  the UI always renders refetched server truth.
- Tables: plain MUI `Table` — no data-grid framework, no virtualization
  (~150 rows ceiling). Desktop-first; mobile capability comes from a
  horizontally scrollable `TableContainer`, not from responsive column
  redesigns.
- Markdown: `react-markdown` + `remark-gfm`, **raw HTML off** (react-markdown
  default; never add `rehype-raw`).
- Search-param state updates use `setSearchParams(..., { replace: true })`
  (filters/tabs/selection are view state; back-button must leave the page,
  not unwind filter clicks).

---

## 1. Route & file map

Routes (extends the pinned Phase-1 route table; React Router v7, package
`react-router`):

```tsx
<Route element={<RequireAdmin />}>
  <Route path="admin" element={<AdminLayout />}>
    <Route index element={<AdminBacklogRoute />} />
    <Route path="models/:motorbikeId" element={<AdminModelReviewRoute />} />
  </Route>
</Route>
```

**Decision: no second admin tab.** The review page is a drill-down of the
backlog (one review per model, reached from a row), not a standalone section —
a "Review" tab would need a list page that merely duplicates the backlog's
`in_review` filter. `AdminLayout` keeps its single **Backlog** tab; the tab
value derivation changes from exact-match to
`pathname.startsWith("/admin") → "backlog"` so the tab stays selected on the
review route. No other `AdminLayout` change.

| Concern | In the URL | Not in the URL |
|---|---|---|
| Backlog status filter | `?status=<backlog\|ingesting\|in_review\|approved\|rejected>`; absent = all; unknown values treated as absent | — |
| Review tab | `?tab=<documents\|specs\|image>`; absent/unknown = `documents` | — |
| Selected document | `?doc=<documentId>`; absent/unknown = first document | — |
| Add-model dialog open state | — | local `useState` |
| Unsaved spec-form edits | — | RHF state |

**Files** (landed convention: routes in `frontend/src/routes/admin/*Route.tsx`,
shared components in `frontend/src/components/`, hooks in
`frontend/src/hooks/`):

| File | Content |
|---|---|
| `frontend/src/routes/admin/AdminBacklogRoute.tsx` | §4. Becomes the `/admin` index route; **`AdminHomeRoute.tsx` is deleted** (it was an explicit placeholder). |
| `frontend/src/routes/admin/AdminModelReviewRoute.tsx` | §6 shell (gates, header, action bar, tabs). |
| `frontend/src/components/AddModelDialog.tsx` | §5. |
| `frontend/src/components/MotorbikeStatusChip.tsx` | §2.1. |
| `frontend/src/components/EmptyState.tsx` | §2.2 — extraction of the Phase-1 empty-state pattern (now used 4+ times). |
| `frontend/src/components/ConfirmDialog.tsx` | §2.3 — shared confirm dialog (approve / reject model / reject image). |
| `frontend/src/components/OperationProgress.tsx` | §3.1 — the graded live-progress element. |
| `frontend/src/components/ModelDocumentsPanel.tsx` | §7. |
| `frontend/src/components/ModelSpecsPanel.tsx` | §8. |
| `frontend/src/components/ModelImagePanel.tsx` | §9. |
| `frontend/src/hooks/useProducts.ts` | `useProducts(statusFilter)`, `useCreateProduct()`, `useTransitionProduct()` (status `PATCH`). |
| `frontend/src/hooks/useOperations.ts` | `useLatestOperationsByEntity()` — see §3.2. |
| `frontend/src/hooks/useProductReview.ts` | `useProduct(id)`, `useProductDocuments(id)`, `useProductImage(id)`, `useSaveDraftSpec(id)`, `useRejectImage()`. |
| `frontend/src/hooks/useServerEvents.ts` | Owned by the job-infrastructure work; §3.3 adds binding requirements on it. |

**Query keys** (invalidation always targets the prefix):

| Key | Query |
|---|---|
| `["products", "list", { status }]` | `GET /api/products` (+ `filter[status]` when set; the hook walks pages via `meta.totalCount`) |
| `["products", "detail", id]` | `GET /api/products/{id}` (specs travel as the product's `draftSpec`/`verifiedSpec` attributes; operation state comes from §3.2, not an include) |
| `["operations", "list"]` | `GET /api/operations` |
| `["documents", productId]` | `GET /api/documents?filter[product]=…` |
| `["productImages", productId]` | `GET /api/product-images?filter[product]=…` |

Mutations invalidate `["products"]` and `["operations"]` on success (blanket
prefix — cheap at this scale, immune to key drift); `useRejectImage`
additionally invalidates `["productImages"]`; the spec save is the one
exception — it invalidates only `["products", "detail", id]` (§8).

---

## 2. Shared building blocks

### 2.1 `MotorbikeStatusChip`

`<Chip size="small" label={t(`admin.status.${status}`)} color={…} />` — one
component so color/label mapping exists exactly once:

| Status | `color` |
|---|---|
| `backlog` | `default` |
| `ingesting` | `info` |
| `in_review` | `warning` |
| `approved` | `success` |
| `rejected` | `error` |

Filled variant (MD2 default). Unknown status values (forward compatibility)
render `default` with the raw value as label.

### 2.2 `EmptyState`

Extraction of the Phase-1 pattern (centered `Stack`, 56px icon in
`text.secondary`, `h6` title, `body2` body capped at 440px, optional action
`Button` last). Props: `icon` (glyph name string), `title`, `body`,
`action?` (ReactNode). Same markup as the Phase-1 spec — do not restyle.

### 2.3 `ConfirmDialog`

`<Dialog maxWidth="xs" fullWidth>` composed of `DialogTitle`,
`DialogContent > DialogContentText`, `DialogActions` with a text `Button`
(cancel, `common.cancel`) and a `variant="contained"` confirm button whose
label and `color` are props. Pending pattern: confirm button `disabled` +
`CircularProgress size={20} color="inherit"` startIcon; cancel disabled;
backdrop-click and Escape dismissal disabled while pending
(`onClose` ignores reasons while the mutation is in flight). A mutation error
renders `<Alert severity="error">` above the body text
(`admin.review.actions.actionError`) and the dialog stays open.

---

## 3. Live progress over SSE (graded pattern)

This UI is the project's graded "progress indicator for long operations".
The mechanism: ingestion runs as a background job whose operation row
(`status: queued | running | succeeded | failed`, `progress` percent,
`message`) is refetched whenever the SSE stream announces
`operation.updated`. **No polling** — SSE invalidation plus the reconnect
rule below is the sole live mechanism.

### 3.1 `OperationProgress`

Props: `operation` (`{ status, progress, message }`), `name` (model
display name, for the `aria-label`), `onRetry?`. Renders a `Stack
spacing={0.5}` sized to its container (table cell or card):

| Operation state | Rendering |
|---|---|
| `queued` | `<LinearProgress variant="indeterminate" />` + `<Typography variant="caption" color="text.secondary">` `admin.backlog.operationQueued`. |
| `running` | `<LinearProgress variant="determinate" value={progress} />` + caption line: `t("admin.backlog.percentComplete", { value: progress })` + ` — ` + `message` (verbatim, see conventions). `progress` is `NOT NULL DEFAULT 0` server-side — no null branch needed. |
| `succeeded` | Renders nothing (the entity's status chip is the signal). |
| `failed` | `<Typography variant="caption" color="error">` `admin.backlog.ingestionFailed` + ` — ` + `message` verbatim, plus the retry button when `onRetry` is given (see §4 row actions). No progress bar. |

The `LinearProgress` gets
`aria-label={t("admin.backlog.progressLabel", { name })}` (MUI supplies
`role="progressbar"` and, for determinate, `aria-valuenow`).

### 3.2 `useLatestOperationsByEntity`

Query `["operations", "list"]` → `GET /api/operations`; `select` reduces the
list to a `Map<entityId, Operation>` keeping the **newest** operation per
referenced motorbike. Consumers (`AdminBacklogRoute`, review ingesting gate)
look up their motorbike id. The full-list fetch is deliberate: the operations
table is small, and one cached query serves every row.

### 3.3 Requirements on `useServerEvents` (binding)

The hook (mounted once in the authenticated shell, per the job-infrastructure
contract) must additionally:

- Map events to prefix invalidations: `operation.updated` →
  `["operations"]`; `product.updated` → `["products"]`;
  `document.updated` → `["documents"]` and `["products"]` (documents are
  fetched via their own endpoint, see §1 query keys).
- Export `useServerEventsStatus(): { connected: boolean }` backed by
  module-level state + `useSyncExternalStore`, so layouts can render
  connection warnings without owning the `EventSource`.
- **On reconnect** (`open` event after any `error`): invalidate
  `["products"]` and `["operations"]` — events during the gap are lost, so a
  blanket refetch restores truth. Native `EventSource` handles the retry
  loop itself; do not implement custom backoff.

**Disconnect surface:** `AdminLayout` renders, between the tabs bar and the
`Outlet`, `<Alert severity="warning" icon={<Icon>sync_problem</Icon>} sx={{ mb: 2 }}>`
with `admin.live.disconnected` — but only after `connected === false` has
persisted for 5 seconds (grace timer; avoids flashing on transient blips).
It disappears on reconnect. One placement covers both admin screens.

---

## 4. AdminBacklogRoute — `/admin`

**Layout** (inside `AdminLayout`'s Outlet, under the Backlog tab):

```
┌ Toolbar row ────────────────────────────────────────────────┐
│ [ Status ▾ (filter) ]                    [ + ADD MODEL ]    │
└─────────────────────────────────────────────────────────────┘
┌ TableContainer (Paper variant="outlined") ──────────────────┐
│ Model            │ Status      │ Ingestion        │ Updated │ (actions)
│ Suzuki GSR 600   │ (ingesting) │ ▓▓▓▓░░ 40%       │ …       │
│                  │             │ fetching 2 of 5… │         │
│ Yamaha MT-07     │ (in review) │                  │ …       │ [REVIEW]
│ Honda CB500F     │ (backlog)   │ ✕ failed — msg   │ …       │ [RETRY]
└─────────────────────────────────────────────────────────────┘
```

- Toolbar row: `<Stack direction="row" spacing={2} sx={{ mb: 2, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>`.
  - Filter: `<TextField select size="small" sx={{ minWidth: 200 }} label={t("admin.backlog.filterLabel")}>`
    with a `MenuItem` per status (`admin.status.*`) plus a first
    `MenuItem value=""` — `admin.backlog.filterAll`. Value mirrors the
    `status` search param; changing it writes the param (empty removes it).
  - Add: `<Button variant="contained" startIcon={<Icon>add</Icon>}>` —
    `admin.backlog.addModel` — opens §5.
- Table: `<TableContainer component={Paper} variant="outlined">` (its default
  overflow-x scroll is the mobile story) wrapping
  `<Table sx={{ minWidth: 720 }} aria-label={t("admin.backlog.table.ariaLabel")}>`
  with `size="medium"`. Columns:
  1. **Model** (`admin.backlog.table.model`) — `<Typography variant="body2">`
     manufacturer + model name (+ year range in `text.secondary` when
     present).
  2. **Status** (`admin.backlog.table.status`) — `MotorbikeStatusChip`.
  3. **Ingestion** (`admin.backlog.table.progress`, width ~35%) —
     `OperationProgress` for the row's latest operation (§3.2) when that
     operation is `queued`/`running`/`failed`; empty cell otherwise.
  4. **Updated** (`admin.backlog.table.updated`) — `updatedAt` via
     `toLocaleString(i18n.language, { dateStyle: "medium", timeStyle: "short" })`.
  5. **Actions** (header `admin.backlog.table.actions`, right-aligned):
     - Status `in_review` → `<Button size="small" component={RouterLink} to={`/admin/models/${id}`}>` — `admin.backlog.review`.
     - Status `backlog` or `rejected` **and** latest operation not
       queued/running →
       `<Button size="small" startIcon={<Icon>refresh</Icon>}>` —
       `admin.backlog.retryIngestion` when the latest operation is `failed`,
       else `admin.backlog.startIngestion` (covers advisor-flagged backlog
       entries that never ran). Click fires `useTransitionProduct` with
       status `ingesting` (the transition `PATCH` re-enqueues ingestion
       server-side); while pending the button shows the standard
       spinner-in-button pattern and is disabled.
     - Status `approved` → row is also clickable through the same Review
       button (read-only review, §6 gates) — same `admin.backlog.review`
       label.
- Row click is **not** a navigation target (buttons only) — avoids
  accidental navigation next to the retry action.

**States:**

| State | Rendering |
|---|---|
| Loading (`isLoading`, no cached data) | Toolbar row renders (Add disabled); table renders headers + 5 placeholder rows, each cell a `<Skeleton variant="text" />`. |
| Background refetch | Keep current rows; no skeletons, no spinner (SSE-driven refetches must be invisible). |
| Error | Toolbar row + `EmptyState` in place of the table: icon `error`, `admin.backlog.loadError` title, `common.errors.serverError` body, action `<Button onClick={refetch}>` `common.retry`. |
| Empty, no filter | `EmptyState`: icon `two_wheeler`, `admin.backlog.emptyTitle` / `emptyBody`, action = the Add-model button (opens §5). |
| Empty, filter active | `EmptyState`: icon `filter_alt_off`, `admin.backlog.emptyFilteredTitle` / `emptyFilteredBody`, action `<Button>` `admin.backlog.clearFilter` (removes the param). |
| Live updates | Rows re-render from SSE-triggered invalidations; a model finishing ingestion flips chip `ingesting → in_review` and the progress cell empties, with **no reload and no route change** — this is the phase's demo moment. |

---

## 5. AddModelDialog

`<Dialog open onClose maxWidth="xs" fullWidth>`; content is a form
(`component="form"` on the content wrapper, submit on Enter):

1. `DialogTitle` — `admin.backlog.addDialog.title`.
2. `DialogContent` with `<Stack spacing={2} sx={{ pt: 1 }}>`:
   - Conditional `<Alert severity="error">` — general errors.
   - `<TextField label={t("admin.backlog.addDialog.nameLabel")} helperText={t("admin.backlog.addDialog.nameHint")} autoFocus required fullWidth />`
     — plain controlled input (this form is login-sized; RHF stays out).
3. `DialogActions`: text `Button` `common.cancel`;
   `<Button type="submit" variant="contained">` —
   `admin.backlog.addDialog.submit` ("Add & start ingestion" — the label
   carries the side effect, no separate explainer text).

Submit → `useCreateProduct` (`POST /api/products`; ingestion auto-starts
server-side).

| State | Rendering |
|---|---|
| Pending | Submit disabled + `CircularProgress size={20}` startIcon; TextField and cancel disabled; dialog non-dismissable (as §2.3). |
| Error — client: empty/whitespace name | Field error `admin.backlog.addDialog.nameRequired` (checked on submit only). |
| Error — 409 (duplicate slug) | Field error on the name field: `admin.backlog.addDialog.duplicate`. |
| Error — 422 | Field error `admin.backlog.addDialog.nameRequired` (only one field to map to). |
| Error — network/5xx | General Alert: `common.errors.serverError`. Value preserved. |
| Success | Close dialog, invalidate `["products"]` + `["operations"]`, and **clear the `status` filter param** so the new row is visible immediately. No snackbar — the new row with its live progress bar is the feedback (Phase-1 rule). |

---

## 6. AdminModelReviewRoute — `/admin/models/:motorbikeId`

Renders inside `AdminLayout` (Backlog tab stays selected). Data:
`useProduct(id)` for the shell, `useProductDocuments(id)` /
`useProductImage(id)` per tab, and, for the ingesting gate,
`useLatestOperationsByEntity`.

**Header** (always rendered once the product is loaded):

```
Backlog / Suzuki GSR 600                       ← Breadcrumbs
┌──────────────────────────────────────────────────────────┐
│ Suzuki GSR 600  (in review)      [ REJECT ] [ APPROVE ]  │
└──────────────────────────────────────────────────────────┘
[ Documents | Specs | Image ]  ───────────── tabs (divider)
<tab panel>
```

- `<Breadcrumbs sx={{ mb: 1 }}>`: `<Link component={RouterLink} to="/admin">`
  `admin.review.back` + `<Typography color="text.primary">` model name.
- Title row: `<Stack direction="row" spacing={2} sx={{ alignItems: "center", flexWrap: "wrap", mb: 2 }}>`
  — `<Typography variant="h5" component="h2">` model name,
  `MotorbikeStatusChip`, `<Box sx={{ flexGrow: 1 }} />`, then the **action
  bar** (only when status is `in_review`):
  - `<Button variant="outlined" color="error">` — `admin.review.actions.reject`.
  - `<Button variant="contained" color="primary" startIcon={<Icon>publish</Icon>}>` — `admin.review.actions.approve`.
  On xs the row wraps; no sticky bar.
- Tabs: `<Tabs value={tab} sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }} variant="scrollable" allowScrollButtonsMobile>`
  with three `Tab`s (`admin.review.tabs.documents|specs|image`); value bound
  to the `tab` search param. Tabs render in every non-gated status —
  approved models are reviewable read-only.

**Approve / Reject flow** — both buttons open `ConfirmDialog` (§2.3):

| Action | Dialog | Mutation | On success |
|---|---|---|---|
| Approve | `approveConfirmTitle` / `approveConfirmBody`; confirm `confirmApprove`, `color="primary"` | `useTransitionProduct` → `PATCH` status `approved` (server promotes draft spec to verified + approves image in one transaction) | Close dialog, invalidate `["products"]` + `["operations"]`, **stay on the page**: chip flips to `approved`, action bar disappears, `approvedNotice` Alert appears (§ gates below). Seeing the published state is the feedback. |
| Reject | `rejectConfirmTitle` / `rejectConfirmBody`; confirm `confirmReject`, `color="error"` | `useTransitionProduct` → `PATCH` status `rejected` (deterministic per the pinned matrix: `in_review → rejected`; the model is re-queueable, draft and documents retained) | Close dialog, invalidate, `navigate("/admin")` — the backlog row, now `rejected` with a retry action, is the feedback. |

An unsaved-edits guard: if the Specs form is dirty, the approve dialog body
appends `admin.review.actions.unsavedWarning` as a second
`DialogContentText` in `color: "warning.main"` — approval promotes the
**saved** draft, not the form buffer.

**Page-level states / gates** (checked in order; gates replace the tabs, the
header always shows):

| State | Rendering |
|---|---|
| Loading | Centered `CircularProgress size={48}` in a `role="status"` Box, `aria-label` `common.loading` — exact Phase-1 guard-spinner markup, breadcrumbs/header withheld until data arrives. |
| Error — 404 | `EmptyState`: icon `search_off`, `admin.review.notFoundTitle` / `notFoundBody`, action `<Button component={RouterLink} to="/admin">` `admin.review.back`. |
| Error — network/5xx | `EmptyState`: icon `error`, `admin.review.loadError` title, `common.errors.serverError` body, retry action (`refetch`). |
| Status `ingesting` (disabled gate) | Instead of tabs: `<Paper variant="outlined" sx={{ p: 4 }}>` containing `<Stack spacing={2}>`: `<Typography variant="h6">` `admin.review.ingestingTitle`, `OperationProgress` (full width) for the model's latest operation, `<Typography variant="body2" color="text.secondary">` `admin.review.ingestingBody`. When SSE flips the status, the refetch swaps this gate for the full review UI automatically — no reload. |
| Status `backlog` / `rejected` | `<Alert severity="info">` `admin.review.backlogNotice` with an embedded `<Button size="small">` (Alert `action` slot) — `admin.backlog.startIngestion` / `retryIngestion` per §4 rules. If the latest operation `failed`, `OperationProgress` renders its failed line beneath the Alert. Tabs still render below (documents/draft may exist from a prior run); action bar hidden. |
| Status `in_review` | Full review UI: tabs + action bar. |
| Status `approved` | `<Alert severity="success" sx={{ mb: 2 }}>` `admin.review.approvedNotice`; tabs render read-only: Specs shows the **verified** spec as a definition list (§8 read-only mode), Image hides the reject button, action bar hidden. |

---

## 7. Documents tab (`ModelDocumentsPanel`)

Master–detail via `<Grid container spacing={3}>`: list pane
`size={{ xs: 12, md: 4 }}`, content pane `size={{ xs: 12, md: 8 }}` (stacks
vertically on mobile — list first, content below; selecting a document on xs
is acceptable without auto-scroll).

**List pane:** `<Paper variant="outlined">` wrapping
`<List aria-label={t("admin.review.documents.listLabel")} disablePadding>`;
one `<ListItemButton selected={…}>` per document (ordering as delivered by
the API — ingestion stores Wikipedia first) with `<ListItemText>`:

- `primary`: `sourceTitle`.
- `secondary`: `t(`admin.review.documents.sourceType.${sourceType}`)` + ` · `
  + `new URL(sourceUrl).hostname`.

Selecting writes the `doc` search param (replace).

**Content pane:** `<Paper variant="outlined" sx={{ p: 3 }}>`:

1. `<Typography variant="h6" component="h3">` — `sourceTitle`.
2. Provenance line, `<Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>`:
   `<Chip size="small" variant="outlined">` sourceType label;
   `<Link href={sourceUrl} target="_blank" rel="noopener noreferrer" variant="body2">`
   showing the full `sourceUrl` (`sx={{ wordBreak: "break-all" }}`);
   `<Typography variant="caption" color="text.secondary">` —
   `admin.review.documents.fetchedAt` with the formatted `fetchedAt` date.
   Provenance (title + URL + type + fetch date) is deliberately user-visible —
   grading requirement.
3. `<Divider sx={{ my: 2 }} />`.
4. The normalized Markdown via
   `<ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: ExternalLink }}>`
   where `ExternalLink` renders MUI `<Link target="_blank" rel="noopener noreferrer">`
   (retrieved-content links never navigate the SPA). Raw HTML stays off.

**States:**

| State | Rendering |
|---|---|
| No documents | `EmptyState` spanning both panes: icon `description`, `admin.review.documents.emptyTitle` / `emptyBody`. |
| `doc` param stale (document deleted / wrong id) | Fall back to the first document; rewrite the param. |
| Loading / error | Handled at page level (§6) — the tab renders only with data present. |

---

## 8. Specs tab (`ModelSpecsPanel`)

**Draft-editing rule (binding): admins edit the DRAFT spec only. Approval
promotes it to verified. The UI never writes `verified` rows.** In status
`approved` this panel renders the verified spec **read-only** as a dense
two-column `<Table size="small">` (field label / value with unit), heading
`admin.review.specs.verifiedHeading` — no form.

In status `in_review` (and `backlog`/`rejected`, where a prior draft may
exist): a **React Hook Form + Zod** form. Heading
`<Typography variant="h6" component="h3">` `admin.review.specs.draftHeading`
with `<Typography variant="body2" color="text.secondary">`
`admin.review.specs.draftHint` beneath ("editing the draft; approving
promotes it").

Fields in `<Grid container spacing={2}>`, each `size={{ xs: 12, sm: 6 }}`:

| Field | Control |
|---|---|
| Engine displacement | `TextField type="number"`, `InputAdornment position="end"` `admin.review.specs.units.cc` |
| Power | same, unit `units.kw` |
| Torque | same, unit `units.nm` |
| Wet weight | same, unit `units.kg` |
| Seat height | same, unit `units.mm` |
| A2 eligible | `TextField select` with three options: `common.unknown` (→ `null`), `common.yes` (→ `true`), `common.no` (→ `false`) — a checkbox cannot express "extractor didn't know", and null matters for the licence-check tool |
| Price band | `TextField select`; options from the generated API enum plus an `common.unknown` (`null`) option; labels via `t(`admin.review.specs.priceBandValues.${value}`, { defaultValue: value })` |
| Category | `TextField select`; same pattern, `categoryValues.*` |

(The price-band and category vocabularies are pinned in
[`shared-knowledge.md`](shared-knowledge.md) — the selects render exactly
those option lists, and the `priceBandValues.*` / `categoryValues.*` i18n
values are filled from them.)

Below the grid: `admin.review.specs.extraHeading`
(`Typography variant="subtitle1"`) + the `extra` JSONB long tail rendered
**read-only** as a dense two-column `<Table size="small">` (key /
stringified value). Not editable in this phase; omitted entirely when `extra`
is empty/absent.

Buttons row (`Stack direction="row" spacing={2} sx={{ mt: 3 }}`):

- `<Button type="submit" variant="contained" disabled={!isDirty || isPending}>` — `admin.review.specs.save`.
- `<Button disabled={!isDirty || isPending} onClick={() => reset()}>` — `admin.review.specs.resetBtn`.

**Zod schema:** every field optional/nullable (drafts legitimately carry
nulls — "leave unknown fields null" is the extraction contract). Numbers:
coerce from the input string, empty string → `null`, otherwise must be a
positive finite number — violation shows field error
`admin.review.specs.errors.numberInvalid` via `error` + `helperText`.
Validation mode `onSubmit` (Phase-1 convention: no keystroke validation).

**Save:** `useSaveDraftSpec` — the draft-spec `PATCH` from the generated
client (upsert semantics server-side, so a missing draft row is not an error
case for the form; it simply starts all-null). **The PATCH is a full-object
replace and the form edits only a subset of the frozen spec fields — the hook
must send the last-fetched `draftSpec` merged with the form values**, so
extraction-filled fields the form doesn't show (`cylinders`, `tankCapacityL`,
`topSpeedKmh`, `abs`, `msrpEur`, `extra`, `sourceHints`) survive a save.

| State | Rendering |
|---|---|
| Pristine | Save + reset disabled. |
| Pending | Save disabled + spinner startIcon; all inputs + reset disabled. |
| Success | Invalidate `["products", "detail", id]`; `reset(formValues)` to the saved values (clears dirty); `<Snackbar autoHideDuration={4000}>` wrapping `<Alert severity="success">` `admin.review.specs.saved` — justified here because saving in place has no other visible change. |
| Error — 422 | Map `loc` field names to matching fields (`numberInvalid`); unmappable → general `<Alert severity="error">` above the form: `common.errors.serverError`. |
| Error — network/5xx | Same general Alert; form values preserved. |
| Draft absent (extraction produced nothing) | The form itself, all fields empty/unknown — **not** an EmptyState; the admin's job is to fill it in. |

---

## 9. Image tab (`ModelImagePanel`)

Single-image model (ingestion fetches one image with variants).

Layout, `<Stack spacing={3} sx={{ maxWidth: 720 }}>`:

1. Status row: `<Chip size="small" label={t(`admin.review.image.imageStatus.${status}`)} color={pending: "warning", approved: "success", rejected: "error"} />`
   plus — when status is `pending` and the model is `in_review` — a
   right-aligned `<Button variant="outlined" color="error" startIcon={<Icon>hide_image</Icon>}>`
   `admin.review.image.reject`.
2. Detail preview: `<Paper variant="outlined" sx={{ p: 2 }}>` containing
   `<Box component="img" src={detailVariantUrl} alt={model name} loading="lazy" sx={{ width: "100%", height: "auto" }} />`.
3. Variant strip: `<Stack direction="row" spacing={2}>` — for `thumb` and
   `card`, a small `img` (`loading="lazy"`, natural size capped via
   `sx={{ maxHeight: 120 }}`) with `<Typography variant="caption" display="block">`
   `admin.review.image.variant.thumb|card` beneath.
4. Attribution block (**always rendered when an image exists** — licence
   display is not optional):
   `<Typography variant="subtitle2">` `admin.review.image.attributionHeading`;
   `<Typography variant="body2" color="text.secondary">` — the stored
   attribution/licence text verbatim, or, when `attribution` is `null`
   (licence metadata unavailable at ingest),
   `admin.review.image.attributionUnknown` — the admin judges such an image
   in review;
   `<Link href={imageSourceUrl} target="_blank" rel="noopener noreferrer" variant="body2">`
   `admin.review.image.sourceLink`.

**Reject flow:** `ConfirmDialog` (§2.3) — `rejectConfirmTitle` /
`rejectConfirmBody`, confirm `admin.review.image.reject`, `color="error"` →
`useRejectImage` mutation. Success: invalidate `["productImages", productId]`;
the chip flips to `rejected`, the reject button disappears, and an
`<Alert severity="info">` `admin.review.image.rejectedNotice` appears
(replacement upload is explicitly a later feature). **Approving a model with
a rejected or absent image is allowed** — the catalogue entry publishes
without an image; there is no separate image-approve button (approval of the
model approves a pending image server-side).

| State | Rendering |
|---|---|
| No image row | `EmptyState`: icon `image`, `admin.review.image.emptyTitle` / `emptyBody`. |
| Rejected | Chip `error` + `rejectedNotice` Alert; previews and attribution stay visible (the admin can still see what was rejected). |
| Model `approved` | Previews + attribution, no reject button. |
| Reject pending / error | §2.3 dialog states. |

---

## 10. i18n keys (merge into `frontend/src/locales/en/translation.json`)

Phase-1 blocks stay; `admin.backlog.emptyTitle`/`emptyBody` **values are
replaced** (they were placeholders). `common` gains keys. The
`priceBandValues` / `categoryValues` sub-blocks are filled at implementation
time from the vocabularies pinned in `shared-knowledge.md` (§8);
`defaultValue` fallback covers gaps.

```json
{
  "common": {
    "loading": "Loading",
    "retry": "Try again",
    "cancel": "Cancel",
    "yes": "Yes",
    "no": "No",
    "unknown": "Unknown",
    "errors": {
      "serverError": "Something went wrong. Please try again."
    }
  },
  "admin": {
    "title": "Admin",
    "tabs": {
      "backlog": "Backlog"
    },
    "live": {
      "disconnected": "Live updates interrupted — reconnecting…"
    },
    "status": {
      "backlog": "Backlog",
      "ingesting": "Ingesting",
      "in_review": "In review",
      "approved": "Approved",
      "rejected": "Rejected"
    },
    "backlog": {
      "filterLabel": "Status",
      "filterAll": "All statuses",
      "addModel": "Add model",
      "review": "Review",
      "retryIngestion": "Retry ingestion",
      "startIngestion": "Start ingestion",
      "operationQueued": "Queued…",
      "percentComplete": "{{value}}%",
      "ingestionFailed": "Ingestion failed",
      "progressLabel": "Ingestion progress for {{name}}",
      "loadError": "Could not load the backlog",
      "emptyTitle": "No models yet",
      "emptyBody": "Add a motorcycle model to start ingestion. It will appear here with live progress and move to review when its documents, specs and image are ready.",
      "emptyFilteredTitle": "No models with this status",
      "emptyFilteredBody": "Nothing in the catalogue currently has this status.",
      "clearFilter": "Show all statuses",
      "table": {
        "ariaLabel": "Motorbike backlog",
        "model": "Model",
        "status": "Status",
        "progress": "Ingestion",
        "updated": "Updated",
        "actions": "Actions"
      },
      "addDialog": {
        "title": "Add model to backlog",
        "nameLabel": "Model name",
        "nameHint": "Manufacturer and model, e.g. “Suzuki GSR 600”",
        "nameRequired": "Enter a model name.",
        "duplicate": "This model is already in the catalogue.",
        "submit": "Add & start ingestion"
      }
    },
    "review": {
      "back": "Backlog",
      "notFoundTitle": "Model not found",
      "notFoundBody": "This model does not exist or was removed.",
      "loadError": "Could not load this model",
      "ingestingTitle": "Ingestion in progress",
      "ingestingBody": "Documents, specs and an image are being collected. Review opens automatically when ingestion finishes.",
      "backlogNotice": "This model has not been ingested yet.",
      "approvedNotice": "This model is published. Specs shown are the verified values.",
      "tabs": {
        "documents": "Documents",
        "specs": "Specs",
        "image": "Image"
      },
      "documents": {
        "listLabel": "Source documents",
        "fetchedAt": "Fetched {{date}}",
        "emptyTitle": "No documents",
        "emptyBody": "Ingestion did not store any source documents for this model.",
        "sourceType": {
          "wikipedia": "Wikipedia",
          "product": "Product page",
          "technical": "Technical documentation",
          "magazine": "Magazine",
          "upload": "Upload"
        }
      },
      "specs": {
        "draftHeading": "Draft specification",
        "draftHint": "You are editing the draft. Approving the model promotes these values to the verified specification.",
        "verifiedHeading": "Verified specification",
        "extraHeading": "Additional extracted data",
        "save": "Save draft",
        "resetBtn": "Discard changes",
        "saved": "Draft saved.",
        "fields": {
          "engineCc": "Engine displacement",
          "powerKw": "Power",
          "torqueNm": "Torque",
          "wetWeightKg": "Wet weight",
          "seatHeightMm": "Seat height",
          "a2Eligible": "A2 eligible",
          "priceBand": "Price band",
          "category": "Category"
        },
        "units": {
          "cc": "cc",
          "kw": "kW",
          "nm": "Nm",
          "kg": "kg",
          "mm": "mm"
        },
        "priceBandValues": {},
        "categoryValues": {},
        "errors": {
          "numberInvalid": "Enter a positive number."
        }
      },
      "image": {
        "imageStatus": {
          "pending": "Pending",
          "approved": "Approved",
          "rejected": "Rejected"
        },
        "variant": {
          "thumb": "Thumbnail",
          "card": "Card"
        },
        "attributionHeading": "Attribution / licence",
        "attributionUnknown": "No licence information could be retrieved for this image — verify before approving.",
        "sourceLink": "Image source",
        "reject": "Reject image",
        "rejectConfirmTitle": "Reject this image?",
        "rejectConfirmBody": "The image will not be published with the model. Uploading a replacement is not available yet.",
        "rejectedNotice": "Image rejected. The model can still be approved without an image.",
        "emptyTitle": "No image",
        "emptyBody": "Ingestion did not fetch an image for this model."
      },
      "actions": {
        "approve": "Approve & publish",
        "reject": "Reject",
        "approveConfirmTitle": "Publish this model?",
        "approveConfirmBody": "The draft specification becomes the verified specification, a pending image is approved, and the model goes live in the catalogue.",
        "confirmApprove": "Publish",
        "rejectConfirmTitle": "Reject this model?",
        "rejectConfirmBody": "The model is marked rejected. Its documents and draft specification are kept — you can restart ingestion from the backlog list.",
        "confirmReject": "Reject",
        "unsavedWarning": "You have unsaved spec edits — approval publishes the last saved draft, not your current changes.",
        "actionError": "The action failed. Please try again."
      }
    }
  }
}
```

---

## 11. Accessibility / UX checklist (applies to §2–§9)

- **Progress semantics:** every `LinearProgress` carries the translated
  `aria-label` (§3.1); determinate mode exposes `aria-valuenow` via MUI. The
  ingesting gate on the review page uses the same component — one
  progressbar semantic everywhere.
- **Dialogs:** MUI `Dialog` handles focus trap / Escape / `aria-labelledby`
  wiring via `DialogTitle`; never dismissable while a mutation is pending
  (§2.3). The Add-model dialog autofocuses its name field.
- **Pending pattern:** identical to Phase 1 — disable the acting control and
  its siblings, spinner as `startIcon` (`CircularProgress size={20}
  color="inherit"`), never a full-page overlay; double-submit prevented by
  `disabled`, not debouncing.
- **Error announcement:** general errors in `<Alert severity="error">`
  (implicit `role="alert"`); field errors via `TextField error + helperText`.
  The SSE disconnect warning is `severity="warning"` — informational, not
  blocking.
- **Links vs buttons:** Review navigation is
  `Button component={RouterLink}` (real href, middle-click works); external
  source/attribution links always `target="_blank"
  rel="noopener noreferrer"`, including links inside rendered Markdown (§7).
- **Retrieved content stays inert:** react-markdown with raw HTML off; no
  `rehype-raw`, no `dangerouslySetInnerHTML` anywhere in the admin UI.
- **Images:** `loading="lazy"` on all previews; `alt` is the model name (the
  attribution text is adjacent visible text, not the alt).
- **Tables:** translated `aria-label` on the backlog table; skeleton rows
  keep the header row so column context is never lost during loading.
- **Color is never the only signal:** status chips pair color with a
  translated label; the failed-operation line pairs `error` color with the
  "Ingestion failed" prefix and message text.
