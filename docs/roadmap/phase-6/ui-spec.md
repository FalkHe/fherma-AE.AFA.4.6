# Phase 6 — UI Specification: Researched identity, claims, trims & used prices

**Binding for the Phase-6 frontend steps** (the identity/claim review surface —
roadmap 6.3 —, the trims editor and customer presentation, and the used-price
surfaces — roadmap 6.4). Produced by the ui-ux-designer, 2026-08-31. Where this
spec and the phase's `shared-knowledge.md` (once sliced) disagree, report the
conflict, don't build either version.

Read first, in this order — this spec deliberately does **not** restate them:

1. [`../model-naming-display-spec.md`](../model-naming-display-spec.md) — the
   landed rendering contract. Its §6.1 (type-code chips), §6.2 (identity panel
   layout, field behaviours, preview, dirty-flag wiring), §6.5 (trims on
   customer surfaces) and §11 (degradation path) are **binding as written**;
   this spec only adds what §6.2/§6.5 left open (exact validation copy, save
   and error flows, the claim surface, reordering, the used-price block).
   Cross-references below are to that document unless marked otherwise.
2. [`../../model-naming.md`](../../model-naming.md) "Implementation decisions
   (owner, 2026-08-31)" and
   [`../model-naming-data-model.md`](../model-naming-data-model.md) §0 (D1–D6),
   §2.2, §2.4, §2.5, §5 — the data shapes.
3. [`../phase-4/ui-spec.md`](../phase-4/ui-spec.md) and
   [`../phase-5/ui-spec.md`](../phase-5/ui-spec.md) — their shared conventions
   continue to apply unchanged: MUI stock components only, palette tokens only,
   Material Symbols via `<Icon>`, all chrome strings through react-i18next
   (§7 lists the new keys), error branching on **HTTP status + `code` only,
   never `detail` text**, validation on submit only, `react-markdown` only via
   `UntrustedMarkdown`, **no new dependencies**.

**No new screens, no new nav entries, no new routes.** Everything below extends
`AdminModelReviewRoute` (`?tab=identity`, per §6.2), `CatalogueModelRoute`, and
`ToolResultCostEstimator`.

Verbatim-rendering exemptions (the standing rule for server/source-derived
display content) extend to: claim strings (`raw`, `manufacturer`, `model`,
`source`, link URLs), trim names and descriptions, used-price source names,
`queryName`, and the recomputed `slug`.

---

## 0. File map

| File | Change |
|---|---|
| `frontend/src/routes/admin/AdminModelReviewRoute.tsx` | 4th tab `identity` (first in order, default stays `documents`); `hasUnsavedSpecs` → `hasUnsavedChanges` (OR of both panels, §6.2); approve-dialog `incomplete-identity` message (§1.6) |
| `frontend/src/components/ModelIdentityPanel.tsx` | **New** — §1 + §3.1 (identity form incl. trims editor; RHF + Zod, `onDirtyChange`, mirrors `ModelSpecsPanel`) |
| `frontend/src/components/ModelClaimPanel.tsx` | **New** — §2 (the unverified-claim block; imported **only** by `ModelIdentityPanel`) |
| `frontend/src/components/ConfirmDialog.tsx` | Optional `errorMessage?: string` prop, default = today's generic text (§1.6) |
| `frontend/src/components/UsedPriceSnapshot.tsx` | **New** — §4 (shared by catalogue detail and chat) |
| `frontend/src/routes/CatalogueModelRoute.tsx` | Trim chip row (§3.2, per §6.5) + used-price block (§4.2) |
| `frontend/src/components/ModelSpecTable.tsx` | Trim-delta group appended (§3.2, per §6.5) |
| `frontend/src/components/ToolResultCostEstimator.tsx` | Renders `UsedPriceSnapshot` when the result carries one (§4.3) |
| `frontend/src/components/toolResults.ts` | `CostEstimatorResult` gains the additive `usedPrice` member (§4.3) — added to this map at slicing time |
| `frontend/src/hooks/useProductReview.ts` | **New** `useSaveIdentity(productId)` mutation (mirrors `useSaveDraftSpec`: typed error with `status` + `code` + validation field pointers) |
| `frontend/src/hooks/useBuildinglines.ts` | **New** — `useBuildinglines(manufacturerId)` (§1.2; `staleTime: 5 * 60_000` like `useManufacturers`) |
| `frontend/src/queryKeys.ts` | `["buildinglines", manufacturerId]` builder |
| `frontend/src/locales/en/translation.json` | §7 keys |

Query invalidation: a successful identity save invalidates
`["products", …]` (the review query) — the response carries the recomputed
`slug`, and the refetched row is the source of truth for the read-only slug
field. No optimistic updates anywhere in this phase.

---

## 1. Admin review — Identity section

Route: `/admin/models/:motorbikeId?tab=identity`. Tab state stays in the URL
(existing `setSearchParams(..., { replace: true })` convention); nothing else
new enters the URL. Layout, field inventory, `Autocomplete` behaviours
(manufacturer over `/api/manufacturers`, buildingline `freeSolo` with
casing-snap-on-blur, type codes `multiple freeSolo` with monospace chips), the
two-level live preview and the dirty-flag wiring are **all pinned in §6.2 —
build them as written there.** This section pins only what §6.2 left open.

### 1.1 Two read-only context rows

Rendered between the type-codes field and the Trims block, as a two-row
`Table size="small"` (the `SpecValueTable` idiom), values verbatim:

| Label (i18n) | Value | Notes |
|---|---|---|
| `admin.identity.slug` | `row.slug`, `Typography` with `fontFamily: "monospace"` | Never editable, never derived client-side — the server recomputes it on save and the refetched row shows the new value. Helper caption below the table: `admin.identity.slugHint`. |
| `admin.identity.queryName` | `row.queryName` in quotes, `text.secondary` | The phrase the admin (or `flag_unknown_bike`) originally typed; context for judging the researched values. |

### 1.2 Options loading (manufacturer + buildingline)

- Manufacturer options: existing `useManufacturers()`.
- Buildingline options: `useBuildinglines(manufacturerId)` — refetches when the
  manufacturer selection changes; disabled (query `enabled: false`) while no
  manufacturer is selected, and the field itself is `disabled` with
  `helperText` `admin.identity.buildinglineNeedsManufacturer` in that case.
- Per the §6.2 pin ("the options must load before the field is usable"): while
  either options query is pending, that field's slot renders
  `<Skeleton variant="rounded" height={56} />` instead of the input. If an
  options query **fails**, render one `Alert severity="warning"` above the form
  (the Phase-5 §3.3 pattern: `sync_problem` icon, `common.retry` button that
  refetches) with `admin.identity.optionsLoadError`; the two `Autocomplete`s
  stay skeletoned/disabled, every other field stays editable.

### 1.3 Validation (Zod, submit-only — the landed convention)

| Field | Rule | Failure message (i18n key) |
|---|---|---|
| `modelName` | trimmed; empty → `null`; ≤ 128 chars | `admin.identity.errors.modelNameTooLong` |
| `buildingline` | trimmed; empty → `null`; ≤ 64 chars | `admin.identity.errors.buildinglineTooLong` |
| `yearFrom`, `yearTo` | empty → `null`; else an integer, 4 digits, `1885 ≤ y ≤ currentYear + 2` | `admin.identity.errors.yearInvalid` |
| `yearFrom`/`yearTo` pair | when both set: `yearTo ≥ yearFrom` (error on `yearTo`) | `admin.identity.errors.yearOrder` |
| `typeCodes` | each entry upper-cased + trimmed on entry; must match `^[A-Z0-9][A-Z0-9\-/ ]{1,31}$`; duplicates dropped silently; ≤ 8 entries | `admin.identity.errors.typeCodeInvalid` / `admin.identity.errors.typeCodesMax` |
| trims | §3.1 | §3.1 |

`yearTo` carries permanent `helperText` `admin.identity.yearToHint` ("empty =
still in production") that is replaced by the error message when erroring —
never both.

Type-code entry rejection (per §6.2): an entry failing the pattern is **not
added** as a chip; the `Autocomplete` keeps the typed text in its input buffer
and the field shows `error` + the helper message until the text changes. The
cap works the same way: the 9th code is refused with `typeCodesMax`, existing
chips untouched.

Nothing is *required* to save — a partially researched identity is a legitimate
draft. Completeness is enforced at **approval**, server-side (§1.6).

### 1.4 Save flow

One explicit save for the whole panel — identity fields **and** trims travel in
one `PATCH /api/products/{id}` `identity` block (§8 API-1):

- Buttons: `Save identity` (contained, `disabled={!isDirty || isPending}`,
  pending state = `CircularProgress size={20}` startIcon + all inputs
  `disabled` — the exact `ModelSpecsPanel` treatment) and `Discard`
  (`form.reset()`).
- Success: `form.reset(form.getValues())`, success `Snackbar`
  (`admin.identity.saved`, autohide 4000 — the specs-panel pattern). The screen
  stays put; the refetched row updates the slug row and the header name.
- The panel reports dirtiness through `onDirtyChange` with a **stable callback**
  and unmount-cleanup, exactly like `ModelSpecsPanel`; the route ORs both
  panels into `hasUnsavedChanges` and feeds the existing approve-dialog
  `unsavedWarning` (§6.2 pinned this — implement it here).

### 1.5 Save errors

Branch on status + code only:

| Response | Surface |
|---|---|
| **409 `duplicate-model`** (slug recompute collided — `DuplicateModelError`) | `Alert severity="error"` directly above the button row: `admin.identity.errors.duplicateIdentity`. Not a field error — the identity is the *triple*, no single field owns it. All typed values kept; the alert clears on the next submit (the `hasGeneralError` idiom). |
| **422 validation** with mappable field pointers | `form.setError(field, { type: "server" })` per mapped field, rendering the same §1.3 messages (the `SaveDraftSpecError.validationFields` idiom, extended to identity + `variants` paths). |
| Anything else (network, 5xx, unmappable 422) | General `Alert severity="error"` with `common.errors.serverError`, values kept. |

### 1.6 Approval and `incomplete-identity`

Approving a row without `manufacturerId`, `modelName` and `yearFrom` returns
**422 code `incomplete-identity`** (data-model §4.2). Surface: the existing
approve `ConfirmDialog` error slot, made specific —

- `ConfirmDialog` gains an optional `errorMessage?: string`; when absent it
  renders exactly today's generic text (zero behaviour change at other call
  sites).
- The route passes
  `transition.error.code === "incomplete-identity" ? t("admin.review.approveBlockedIdentity") : undefined`.
- Copy: *"This model cannot be published yet: manufacturer, model name and
  start year must be filled in the Identity tab first."* The dialog stays open;
  cancel returns the admin to the page where the Identity tab is one click away.

### 1.7 Read-only when approved

Same rule as the specs panel: `status === "approved"` renders the identity as a
read-only `SpecValueTable`-style table (manufacturer, buildingline, model name,
year range via the §1.3 year-range formatting of the display spec, type codes
as §6.1 chips, slug, queryName) plus the read-only trims list (§3.1 read-only
rendering) — no form, no claim actions (the claim panel itself still renders,
collapsed, for provenance). Every other status gets the editable form.

### 1.8 States (identity tab)

| State | Treatment |
|---|---|
| Loading (product) | Route-level `CircularProgress` gate — unchanged. |
| Loading (options) | Field-slot `Skeleton`s, §1.2. |
| Empty (all identity fields null) | The form itself, all fields blank — a blank form **is** the empty state; no `EmptyState` component. The preview clamps per display-spec §1.2 and shows `queryName` verbatim at both levels when `modelName` is null (§11 fallback — never an empty parenthesis). |
| Error (options) | Warning `Alert` + retry, §1.2. |
| Error (save) | §1.5. |
| Saving | Disabled form + button spinner, §1.4. |

**Test hooks:** save 409 → duplicate alert, values kept; save 422 with
`yearFrom` pointer → field error; approve stubbed to 422 `incomplete-identity`
→ dialog shows the specific message; typing an invalid type code → no chip, and
helper error; buildingline options pending → skeleton, no free typing possible;
dirty identity + approve → `unsavedWarning` in the dialog.

---

## 2. Claim vs. finding (roadmap 6.3)

`motorbikes.suggestion` is an **unverified claim** imported from a list
(`app suggestions import`), shape (snake_case in the JSONB, camelCase on the
wire per §8 API-1):

```json
{ "source": "bike-list.txt", "raw": "BMW R 1250 GS (K50) 2019–2023 ([Wikipedia][3])",
  "manufacturer": "BMW", "model": "R 1250 GS", "year_from": 2019, "year_to": 2023,
  "in_production": false, "year_ranges": [{"from": 2019, "to": 2023}],
  "type_codes": ["K50"], "links": ["https://…"] }
```

### 2.1 The hard boundary — stated once, enforced twice

**A claim is never rendered as catalogue data anywhere a customer can see it.**
Where the boundary sits in the component tree:

- **Wire boundary:** `suggestion` is a member of the admin `products` resource
  **only**. The customer `catalogue-models` resources must never carry it
  (§8 API-2). Because the frontend's types are generated from the OpenAPI
  schema, the customer `CatalogueModelDetail` type simply has no such member —
  `pnpm typecheck` is the fence.
- **Component boundary:** the only component that accepts claim data is
  `ModelClaimPanel`, and its only importer is `ModelIdentityPanel`, whose only
  importer is `AdminModelReviewRoute` (under `RequireAdmin`). No component in
  `frontend/src/components/` that a customer route imports may accept a
  `suggestion`/claim prop — pin this as a doc comment on `ModelClaimPanel`.
- "Use the claim" (§2.3) **fills the form buffer only.** A claimed value
  becomes catalogue data exactly when the admin saves it into the typed
  identity columns and later approves — i.e. through the same path as a typed
  value, never by rendering the claim itself.

### 2.2 The claim panel

Rendered at the **top of the Identity tab**, above the form, only when
`row.suggestion` is non-null (absent claim = no panel, no placeholder):

```
┌ Paper variant="outlined" ───────────────────────────────────────────┐
│ [⚑ Unverified claim]  (Chip size=small color=warning variant=outlined,
│                        icon <Icon>flag</Icon>)
│ Imported from a suggestion list — research must confirm it before   │
│ it becomes catalogue data.               (caption, text.secondary)  │
│                                                                     │
│ Listed as   "BMW R 1250 GS (K50) 2019–2023"     (verbatim, quoted)  │
│ Source      bike-list.txt                        (verbatim)         │
│ Suggested links   en.wikipedia.org/…  ↗   …  ↗                      │
└─────────────────────────────────────────────────────────────────────┘
```

- `raw` and `source` render as plain `Typography` — **plain text, never
  markdown** (they are file-derived strings; React's escaping is the renderer;
  `UntrustedMarkdown` is not used because no markdown semantics are wanted).
- `links`: MUI `Link` per URL, label = the URL itself (truncated with
  `wordBreak: "break-word"`), `target="_blank" rel="noopener noreferrer"` —
  the `ExternalLink` treatment. These are research input for the admin to open;
  they have no "use" action.
- Collapsible via a stock `Accordion`? **No** — always expanded. The panel is
  the reason the tab exists for imported rows; hiding it invites approving a
  form against nothing. (When the row is approved, §1.7, it renders inside a
  collapsed `Accordion` with the chip in the summary — history, not a task.)

### 2.3 Per-field claim rows — "use the claim"

Under each identity form field that has a corresponding claim value, one claim
row (`Stack direction="row" spacing={1} alignItems="center"`):

```
Claim: 2019–2023        [ Use claim ]
(caption, text.secondary) (Button size="small" variant="text")
```

| Form field | Claim value shown | "Use claim" fills |
|---|---|---|
| Manufacturer | `suggestion.manufacturer` verbatim | The `Autocomplete` selection — **only rendered as a button when** a case-insensitive match exists in the loaded manufacturer options; otherwise the row shows the claim text plus caption `admin.identity.claim.noManufacturerMatch` and **no button** (the manufacturer table is curated; the form cannot invent a row). |
| Model name | `suggestion.model` verbatim | The text field. |
| Year from / Year to | The claimed range, formatted like the CLI summary: `2019–2023`, `from 2019` (`in_production`), single year. When `year_ranges` has **more than one** entry, list them all in the caption (`2019–2023 · from 2024`) — the button fills `year_from = min`, `year_to = null if in_production else max`, mirroring the import's own collapse rule. | Both year fields at once. |
| Type codes | `K50` (joined with `/` if several) | **Union** into the chips: claimed codes not already present are appended (they are pre-normalised by the import); entries that would exceed the cap of 8 are not added and the field shows `typeCodesMax`. |

Rules:

- Filling **marks the form dirty** (`setValue(..., { shouldDirty: true })`) and
  never saves. The button is `disabled` while the form is saving.
- A claim row renders only when the claim member is non-null; a field without a
  claim gets no row (no "no claim" placeholder).
- Claim values in these rows are `Typography variant="caption"` — deliberately
  *lighter* than the form values. The visual hierarchy is: researched/typed
  value (the input) loud, claim quiet. The claim is never pre-filled into an
  empty form automatically — an admin action is the promotion, always.

### 2.4 Contradiction warnings from the ingestion run

Roadmap 6.2: a claimed year range the sources contradict is recorded as a
**warning on the run** — it arrives as text in `operation.message` with the
prefix `WARNING_SUMMARY_PREFIX = "Completed with warnings: "`
(`backend/app/services/ingestion/service.py:76`).

- The route already holds the row's latest operation
  (`useLatestOperationsByEntity`); pass it into `ModelIdentityPanel` as an
  optional `operation` prop.
- When `operation.status === "succeeded"` and
  `operation.message?.startsWith(WARNING_SUMMARY_PREFIX)`, render an
  `Alert severity="warning" icon={<Icon>report</Icon>}` **between the claim
  panel and the form**: title line `admin.identity.researchWarnings`
  ("Research finished with warnings"), body = `operation.message` with the
  prefix stripped, rendered **verbatim** as plain text (server-composed
  English — the standing exemption). Not dismissible: it re-renders until the
  next run replaces the operation, which is correct — the warning is a property
  of the data on screen.
- Duplicate the prefix as a frontend module constant with a comment naming the
  backend source file — a **fragile string contract**; note in the step file
  that a backend rename must touch both. (A structured `hasWarnings` flag is
  the better long-term shape — §9 OQ-2.)
- Failed operations keep their existing `OperationProgress` surface on the
  route; this Alert handles succeeded-with-warnings only.

**Test hooks:** suggestion present → panel + per-field rows; "use claim" on
years fills both fields and dirties the form; manufacturer claim with no
matching option → text + no button; suggestion null → no panel; operation
message with the prefix → warning Alert with the stripped message; customer
detail fixture has no `suggestion` member (type-level, compile-time).

---

## 3. Trims (`variants`)

Data shape: data-model §2.5 — `{ slug, name, specs?, description? }[]`, order =
display order, base never an entry, ≤ 20 entries, `description` ≤ 400 chars,
`specs` keys restricted to the frozen spec columns.

### 3.1 Admin editor (inside the Identity panel)

Layout per §6.2 (a `List` of `Card variant="outlined"` rows under the heading
`admin.identity.variants.heading`, preceded by the base hint
`admin.identity.variants.baseHint`). Implementation pins beyond §6.2:

- **RHF `useFieldArray`** over `variants` inside the identity form — one form,
  one save (§1.4). `slug` is **not** edited: the server derives it as
  `slugify(name)`; the client never sends it.
- Per-trim controls:
  - name `TextField` (required, ≤ 64, unique case-insensitively within the
    list — errors `nameRequired` / `nameDuplicate`);
  - `description` multiline `TextField` (3 rows), ≤ 400; `helperText` is a live
    character counter `admin.identity.variants.descriptionCount`
    (`"{{count}}/400"`), turning into the error message on overflow at submit;
  - delta-spec rows: a `Select` over exactly the eight fields
    `ModelSpecsPanel` edits (`engineCc`, `powerKw`, `torqueNm`, `wetWeightKg`,
    `seatHeightMm`, `a2Eligible`, `priceBand`, `category`) reusing the
    `admin.review.specs.fields.*` labels, plus a value input typed per field
    (number `TextField` with the unit `InputAdornment` and the positive-finite
    rule / yes-no `Select` for `a2Eligible` — **no "unknown" option**: an
    absent key already means "same as the base" / enum `Select` for
    `priceBand`/`category`), plus a remove `IconButton`
    (`<Icon>delete</Icon>`, `aria-label` `variants.removeSpec`). A field
    already used by this trim disappears from the `Select` options; "Add
    difference" (`Button size="small"` + `add` icon) appends a row and is
    hidden when all eight are used;
  - **reorder** = display order: an `IconButton` pair per card
    (`arrow_upward` / `arrow_downward`, `aria-label`s `variants.moveUp` /
    `moveDown`), first/last disabled respectively, wired to
    `fieldArray.move()`. No drag-and-drop (no dependency exists for it);
  - remove-trim `IconButton` (`delete`, `aria-label` `variants.remove`) in the
    card header — no confirm dialog (the change is not saved until "Save
    identity"; Discard is the undo).
- "Add trim" `Button` (`add` icon) after the list; `disabled` at 20 entries
  with a caption `admin.identity.variants.errors.max` beside it.
- **Empty state is normal, not an error:** zero entries render the heading,
  the base hint, one `Typography variant="body2" color="text.secondary"` line
  `admin.identity.variants.empty` ("No trims recorded — this entry is the base
  model.") and the Add button. No `EmptyState` component, no warning colour.
- Read-only (approved, §1.7): the same cards without inputs — name as
  `subtitle2`, description as `body2`, deltas as one composed line each (the
  §6.5 customer composition), no buttons.

### 3.2 Customer presentation (catalogue detail)

Build **exactly** display-spec §6.5 — chip row directly under the `h1` (one
outlined `Chip` per entry, `description` as `Tooltip` with `describeChild`;
chips link nowhere; empty `variants` renders nothing at all), and the per-trim
delta line inside the spec area. The one composition pin §6.5 left open:

- The delta lines render as a final group appended to `ModelSpecTable`, titled
  `catalogue.detail.trims.heading` ("Trims") in the table's existing
  group-heading style, one row per trim **that has `specs`**: cell 1 = trim
  name (verbatim, `fontWeight: 600`), cell 2 = deltas joined with ` · `, each
  formatted through the existing `specFields.ts` value+unit formatting
  (`30 l tank` → use the field's short label + unit exactly as the comparison
  tool renders them). Trims without `specs` (description-only packages) appear
  in the chip row only — no table row, per "the customer reads *what differs*".
- Never phrase the group as a filter promise (D4): the group heading is
  "Trims", not "Also available with…".
- A trim with a description but no tooltip-capable device: MUI `Chip` is
  focusable when it has a Tooltip; the description is additionally the chip's
  `aria-describedby` via `describeChild` — display-spec §8 rule 3/4 satisfied.

States: the detail page's existing full-page skeleton/error handling covers
the trims (they arrive on the same payload); a payload without `variants`
(older API) renders nothing — the §11 degradation path.

**Test hooks:** editor — add/edit/reorder/remove trims, save, panel resets
clean; 21st trim refused; duplicate name errors; delta field disappears from
the Select once used. Customer — fixture with two trims (one with specs) →
two chips + one delta row; empty `variants` → no chips, no group.

---

## 4. Used price (roadmap 6.4)

### 4.1 The shape and the one component

The frontend needs, per model (proposed wire names — **API requirement**
§8 API-3, not yet on any endpoint; flag any deviation rather than adapting
silently):

```ts
// Pinned by shared-knowledge.md D11 — these are the final wire names, not a
// proposal. The block is additive on both the cost-estimator tool result and
// the catalogue-models *detail* resource (never the list).
type UsedPrice = {
  medianEur: number;
  minEur: number;              // low end of observed asking prices
  maxEur: number;              // high end
  sampleCount: number | null;  // null = unknown, never "zero"
  asOf: string;                // ISO timestamp of the research run
  stale: boolean;              // the SERVER's verdict — see below
  sources: { title: string; url: string }[];  // >= 1 — per-source provenance
};
```

**Currency is not in the block.** Every price in this application is EUR (the
columns are `price_*_eur`). The shared component takes a `currency` prop
defaulting to `"EUR"`; the chat surface passes the estimator result's existing
top-level `result.currency`, which is the landed idiom.

One shared component, `frontend/src/components/UsedPriceSnapshot.tsx`
(presentational, data as props, translates its own chrome via
`common.usedPrice.*`), used by both surfaces so the "snapshot, never a fact"
framing cannot drift between them:

```
Used market price   [ ⏱ Market snapshot ]        ← subtitle1 + Chip size=small
                                                    variant=outlined color=warning
                                                    icon <Icon>schedule</Icon>
€6,400 – €9,200     (h6)      Median €7,800  ·  23 listings observed
                              (caption, text.secondary)
Asking prices observed on the linked marketplaces — a dated snapshot,
not a valuation.                                 (caption, text.secondary)
Sources: kleinanzeigen.de ↗ · mobile.de ↗ — as of 14 Aug 2026
                                                 (caption; Links external)
[ stale === true only: ]
⚠ This snapshot is older than the market-data window and may no longer
  reflect current prices.   (Typography caption color="warning.main"
                      + <Icon fontSize="small">history</Icon>)
```

Pins:

- **Numbers:** `Intl.NumberFormat(i18n.language, { style: "currency", currency,
  maximumFractionDigits: 0 })` — the exact `ToolResultCostEstimator` idiom.
  Range via `common.usedPrice.range` (`"{{min}} – {{max}}"`).
- **Date:** `Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" })` over
  `asOf`, interpolated through `common.usedPrice.asOf` (`"as of {{date}}"`).
  The date is **always visible** — it is what makes the number honest.
- **Sample count:** `sampleCount === null` → `common.usedPrice.sampleUnknown`
  ("Sample size unknown") in the same caption slot — an unknown count is
  stated, never hidden, because it weakens the number.
- **Provenance:** every source renders as a MUI `Link` (name verbatim,
  `href=url`, `target="_blank" rel="noopener noreferrer"`), joined with ` · ` —
  in the running caption, **never** behind a tooltip or toggle
  (user-visible provenance is a grading requirement).
- **Stale state:** driven **only** by the payload's `stale` boolean. It is a
  server verdict (`USED_PRICE_MAX_AGE_DAYS`, default 180 — shared-knowledge
  D10), so the advisor's prose and this caption can never disagree, and the
  threshold is tunable without a frontend release. **Do not compute staleness
  on the client and do not hard-code a day count** — the caption is
  `common.usedPrice.stale` (§7), which is deliberately worded without a day
  figure so the server-side threshold can change without a translation
  update. There is no `staleDays` key. The snapshot
  chip and all values keep rendering; the stale caption is **added**, colour
  paired with the `history` icon and full-sentence text (colour never the only
  signal). Data is not suppressed: an old snapshot with a date is more honest
  than nothing.
- **Malformed guard:** if `minEur`, `maxEur`, `medianEur`, `asOf` or a non-empty
  `sources` is missing, render nothing (null discipline — a price block
  without provenance would read as a fact, which is the one forbidden state).

### 4.2 Catalogue detail block

`CatalogueModelRoute`, rendered as a full-width section **between the
image/spec `Grid` and the "About" article**, wrapped in
`<Paper variant="outlined" sx={{ p: 2, mt: 4 }}>`:

- Present: the §4.1 component.
- **Absent** (`usedPrice === null` or member missing): **nothing renders** —
  no heading, no "no price yet" line. Rationale: most models will have no
  researched price for a long time (the roadmap says so); a permanent absence
  notice on most detail pages is noise, and the landed precedent (article,
  trims, image fallbacks) is that absent catalogue content renders nothing.
  The MSRP/price-band chips elsewhere on the page are untouched — they are
  new-bike fields and must not be conflated (roadmap 6.4).
- Loading/error: covered by the page-level skeleton and error states — the
  snapshot arrives on the detail payload; no block-level spinner.

### 4.3 In chat — the cost estimator result

`CostEstimatorResult` gains an optional `usedPrice?: UsedPriceSnapshot`
(§8 API-4). `ToolResultCostEstimator` renders `<UsedPriceSnapshot …/>` **after
the assumptions block**, inside the existing tool frame (no extra `Paper` —
the frame is the container), separated by `Divider sx={{ my: 1 }}`.

- The existing line items, total, "Estimate" chip and assumptions are
  **unchanged** — the server-composed labels stay verbatim (display-spec §10).
  Whether the estimator's purchase line *uses* the researched median is a
  backend concern; the UI renders whatever lines arrive.
- Absent `usedPrice`: the block simply does not render — today's rendering,
  byte-identical. This **is** the defined absent state in chat: the estimator
  already discloses "Estimate" on guess-based numbers, and that disclosure
  continues to carry the no-research case.
- Persisted tool results keep whatever snapshot they were written with —
  a three-month-old transcript shows the (now stale-flagged, §4.1) snapshot it
  was answered with; never re-fetched, matching the display-spec §1.4
  persistence rule. The persisted tool result keeps the `stale` value the
  server computed **at that turn**, so an old transcript shows what the
  advisor actually said at the time — which is the honest reading of a
  transcript, and one less thing to recompute.
- The `seen → typing… → message` rhythm, progress indicators and SSE handling
  are untouched — this is one more block inside an existing tool result.

**Test hooks:** component — formats range/median/count, unknown count string,
stale caption when `stale: true` and none when `stale: false`, renders every source
as an external link, renders nothing when `sources` is empty. Catalogue —
fixture with/without `usedPrice` → block present/absent. Chat — estimator
result with `usedPrice` renders it after assumptions; without it, snapshot DOM
absent and the rest byte-identical.

---

## 5. Screen × state matrix (QA walkthrough)

| Surface | Loading | Empty | Error | Stale / warning |
|---|---|---|---|---|
| Identity tab — form | route gate (existing) + field `Skeleton`s for the two option lists (§1.2) | blank form + `queryName` fallback preview (§1.8) | options warning Alert + retry (§1.2); save 409/422/5xx (§1.5); approve 422 `incomplete-identity` in dialog (§1.6) | research-warning Alert (§2.4) |
| Identity tab — claim panel | n/a (same payload as the row) | no suggestion → no panel (§2.2) | n/a | "Unverified claim" chip is permanent (§2.2) |
| Identity tab — trims editor | with the form | `variants.empty` line + Add (§3.1) | per-field submit errors (§3.1); save errors shared with §1.5 | n/a |
| Catalogue detail — trim chips + delta group | page skeleton (existing) | renders nothing (§6.5) | page error states (existing) | n/a |
| Catalogue detail — used price | page skeleton (existing) | renders nothing (§4.2) | page error states (existing); malformed → nothing (§4.1) | stale caption when `stale === true` (§4.1) |
| Chat — cost estimator snapshot | existing typing/tool rhythm | absent member → today's rendering (§4.3) | existing tool-result error handling | stale caption from the payload flag (§4.3) |

---

## 6. Accessibility additions (prior checklists still apply)

- Type-code and trim chips: the §6.1/§8 display-spec `aria-label` rules apply
  as written.
- "Use claim" buttons carry
  `aria-label={t("admin.identity.claim.useA11y", { field })}` (e.g. "Use the
  claimed model name") — five identical visible labels on one form are
  distinguishable only by context a screen reader may not have.
- Reorder `IconButton`s: translated `aria-label`s; after a move, focus stays on
  the clicked button (MUI default) so repeated moves need no re-focusing.
- The claim panel's chip + caption pair means "unverified" is carried by text,
  not colour alone; same for the stale caption (icon + sentence).
- The research-warning `Alert` has `role="alert"` (MUI default) — announced
  without focus theft.
- The used-price source links are real links with the domain as text — no
  icon-only affordances.

---

## 7. i18n keys (merge into `frontend/src/locales/en/translation.json`)

Display-spec §9 keys (`admin.review.tabs.identity`, `admin.identity.*` labels
and hints named there, `catalogue.detail.trims.*`, `common.modelName.*`) are
already pinned; the table below gives **exact values** for those left as
placeholders there plus everything new in this spec. Claim values, trim
names/descriptions, source names and `operation.message` bodies are verbatim
(never translated).

```json
{
  "admin": {
    "identity": {
      "manufacturer": "Manufacturer",
      "buildingline": "Buildingline",
      "buildinglineHint": "Model family used for grouping — pick an existing spelling when one exists.",
      "buildinglineNeedsManufacturer": "Select a manufacturer first.",
      "modelName": "Model name",
      "modelNameHint": "The marketing name without manufacturer, trim or year — e.g. R 1300 GS.",
      "yearFrom": "Year from",
      "yearTo": "Year to",
      "yearToHint": "Leave empty if the model is still in production.",
      "typeCodes": "Type codes",
      "slug": "Slug",
      "slugHint": "Derived from manufacturer, model and year range — recomputed when you save.",
      "queryName": "Originally entered as",
      "save": "Save identity",
      "discard": "Discard",
      "saved": "Identity saved.",
      "optionsLoadError": "Manufacturer or buildingline suggestions could not be loaded.",
      "researchWarnings": "Research finished with warnings",
      "errors": {
        "modelNameTooLong": "At most 128 characters.",
        "buildinglineTooLong": "At most 64 characters.",
        "yearInvalid": "Enter a four-digit year.",
        "yearOrder": "\"Year to\" must not be before \"Year from\".",
        "typeCodeInvalid": "Codes are 2–32 characters: letters, digits, hyphen, slash or space.",
        "typeCodesMax": "At most 8 codes.",
        "duplicateIdentity": "Another catalogue entry already has this manufacturer, model name and start year."
      },
      "claim": {
        "heading": "Unverified claim",
        "hint": "Imported from a suggestion list — research must confirm it before it becomes catalogue data.",
        "listedAs": "Listed as",
        "source": "Source",
        "links": "Suggested links",
        "value": "Claim: {{value}}",
        "use": "Use claim",
        "useA11y": "Use the claimed {{field}}",
        "noManufacturerMatch": "No matching manufacturer in the catalogue."
      },
      "variants": {
        "heading": "Trims",
        "baseHint": "This catalogue entry is the base trim; list only what a trim changes or adds.",
        "empty": "No trims recorded — this entry is the base model.",
        "add": "Add trim",
        "remove": "Remove trim",
        "moveUp": "Move up",
        "moveDown": "Move down",
        "name": "Trim name",
        "description": "Description",
        "descriptionCount": "{{count}}/400",
        "addSpec": "Add difference",
        "removeSpec": "Remove difference",
        "specField": "Specification",
        "specValue": "Value",
        "errors": {
          "nameRequired": "Every trim needs a name.",
          "nameDuplicate": "Trim names must be unique.",
          "descriptionTooLong": "At most 400 characters.",
          "max": "At most 20 trims."
        }
      }
    },
    "review": {
      "approveBlockedIdentity": "This model cannot be published yet: manufacturer, model name and start year must be filled in the Identity tab first."
    }
  },
  "catalogue": {
    "detail": {
      "trims": {
        "heading": "Trims"
      }
    }
  },
  "common": {
    "usedPrice": {
      "heading": "Used market price",
      "snapshotChip": "Market snapshot",
      "range": "{{min}} – {{max}}",
      "median": "Median {{median}}",
      "sampleCount": "{{count}} listings observed",
      "sampleUnknown": "Sample size unknown",
      "asOf": "as of {{date}}",
      "disclaimer": "Asking prices observed on the linked marketplaces — a dated snapshot, not a valuation.",
      "sources": "Sources",
      "stale": "This snapshot is older than the market-data window and may no longer reflect current prices."
    }
  }
}
```

---

## 8. API requirements (frontend needs — the architect owns final wire names)

Field names below reuse the pins in
[`../model-naming-data-model.md`](../model-naming-data-model.md) §6 ("API
schemas" row) wherever one exists; only the members marked *proposed* are new
names this spec introduces — **flag, don't improvise**, if the backend lands
different ones.

| # | Requirement |
|---|---|
| API-1 | Admin `products` resource carries `queryName`, `buildingline`, `typeCodes`, `variants`, path-shaped `slug`, and **`suggestion`** (*proposed*: the JSONB verbatim, camelCased: `source, raw, manufacturer, model, yearFrom, yearTo, inProduction, yearRanges[{from,to}], typeCodes[], links[]`; `null` when none). `PATCH /api/products/{id}` accepts a writable `identity` block: `{ manufacturerId, buildingline, modelName, yearFrom, yearTo, typeCodes, variants }` — full-object replace, response carries the recomputed `slug`; 409 `duplicate-model` on collision; 422 with field pointers on validation. |
| API-2 | The customer `catalogue-models` resources must **not** carry `suggestion` or `typeCodes` (display-spec §1.1 rule); the detail **does** carry `variants`. |
| API-3 | **Pinned (shared-knowledge D11):** the catalogue-models **detail** resource gains `usedPrice: null \| { medianEur, minEur, maxEur, sampleCount, asOf, stale, sources[{title,url}] }` (§4.1). The **list** resource does not carry it (no price research on a card, and no N+1). |
| API-4 | **Pinned (shared-knowledge D11):** the `cost_estimator` tool result gains an additive `usedPrice` of the same shape (persisted with the message, like every tool result). Every landed field of that result keeps its key and type. |
| API-5 | Buildingline options (**in scope for step 6.20**): a read endpoint listing a manufacturer's distinct `buildingline` values (data-model §4.1 `list_buildinglines`) — *proposed* `GET /api/manufacturers/{id}/buildinglines` → `string[]`; any admin-readable shape works, the hook adapts. |
| API-6 | Approving an identity-incomplete row returns **422 code `incomplete-identity`** (data-model §4.2) — the frontend branches on that code (§1.6). |
| API-7 | `operation.message` keeps the `"Completed with warnings: "` prefix contract (§2.4) — renaming it is a coordinated two-repo-location change. |

After the backend lands: `make generate-api`, then `pnpm typecheck` proves the
shapes.

---

## Open questions

Everything else in this spec picks a default and says so. Genuinely open:

| # | Question | Default taken meanwhile |
|---|---|---|
| ~~OQ-1~~ | ~~Should "stale" be a server verdict instead of the client's 90-day constant?~~ | **Closed by the coordinator at slicing time: server verdict.** `stale` is on the wire (shared-knowledge D11) and computed from `USED_PRICE_MAX_AGE_DAYS` (D10). The client renders the flag and never computes a threshold. §4.1 updated. |
| OQ-2 | Should succeeded-with-warnings become a structured member on the operation payload (`hasWarnings: boolean` + `warnings: string[]`) instead of the string-prefix contract (§2.4)? | Parse the pinned prefix, constant duplicated with a source comment; flagged as fragile in API-7. |
| OQ-3 | When a researched used price exists, should the catalogue detail also *hide or annotate* the guess-based `priceBand` chip (Phase-4 OQ2 numbers) to avoid two price signals? | Both render (§4.2): the band is a new-bike classification, the snapshot is the used market — different claims, both labelled. Owner may prefer suppression. |
