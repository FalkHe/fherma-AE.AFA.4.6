---
phase: 6
step: "6.25"
title: Trims editor and the customer trims block, UI-only
summary: The variants field-array editor inside the identity form (one form, one save, matching assign_identity's full-object replace) and the customer presentation — chip row under the h1 plus the delta group appended to ModelSpecTable; still stubs, empty state is normal copy.
effort: 4
dependencies: ["6.24"]
---

# Step 6.25 — Trims editor and the customer trims block, UI-only

**Effort: 4** — a field array with per-trim delta-spec sub-editors,
reordering and its validation matrix, plus two customer surfaces and tests;
still entirely against stubs/fixtures.

Binding contract: `docs/roadmap/stage-01/phase-6/shared-knowledge.md` (D1 — the §2.5
variants shape and caps, D2 — one save, full-object replace) and
**`docs/roadmap/stage-01/phase-6/ui-spec.md` §3.1, §3.2, §7** with
`docs/roadmap/stage-01/phase-6/model-naming-display-spec.md` §6.2 (editor layout), §6.5
(customer trims), §11 (degradation). Agent: **frontend-dev**. Zero
deviations — a deviation is a stop-and-report.

**Environment:** stubs only; `make frontend-test` runs with the stack down.
Backend track continues concurrently — do not touch `backend/`.

## Outline

- `frontend/src/components/ModelIdentityPanel.tsx`: the trims editor per
  ui-spec §3.1, **inside the identity form** — RHF `useFieldArray` over
  `variants`, so identity fields and trims travel in **one**
  `PATCH /api/products/{id}` `identity` block (§1.4; the client never
  sends a trim `slug` — the server derives it). Per-trim controls exactly
  as pinned: name (required, ≤ 64, case-insensitively unique), description
  (3-row multiline, ≤ 400, live `{{count}}/400` counter that becomes the
  error at submit), delta-spec rows (a `Select` over exactly the eight
  `ModelSpecsPanel` fields — `engineCc`, `powerKw`, `torqueNm`,
  `wetWeightKg`, `seatHeightMm`, `a2Eligible`, `priceBand`, `category` —
  reusing `admin.review.specs.fields.*` labels, typed value inputs, used
  fields removed from the options, "Add difference" hidden at eight),
  reorder via `arrow_upward`/`arrow_downward` `IconButton`s wired to
  `fieldArray.move()` (first/last disabled), remove without confirm
  (Discard is the undo). "Add trim" disabled at 20 with the `max` caption.
- **Empty state is normal copy, never an error** (§3.1 pin): heading, base
  hint, the `admin.identity.variants.empty` line and the Add button — no
  `EmptyState` component, no warning colour.
- Read-only when approved (§1.7/§3.1): the same cards without inputs —
  name `subtitle2`, description `body2`, deltas as one composed line each,
  no buttons.
- Customer — `frontend/src/routes/CatalogueModelRoute.tsx`: chip row
  directly under the `h1` per display-spec §6.5 (one outlined `Chip` per
  entry, `description` as `Tooltip` with `describeChild`, chips link
  nowhere, empty renders nothing at all).
- Customer — `frontend/src/components/ModelSpecTable.tsx`: optional
  `variants` prop; a final group appended in the existing group-heading
  style, titled `catalogue.detail.trims.heading`, one row per trim **that
  has `specs`** — cell 1 trim name verbatim `fontWeight: 600`, cell 2
  deltas joined with ` · `, each through the existing `specFields.ts`
  value+unit formatting. Description-only trims stay chips-only. Never
  phrased as a filter promise (D1's known gap).
- Typing/stubs: the catalogue detail payload has no `variants` until 6.23
  — add a local optional member (removed in 6.28) and handle absence per
  §11 (renders nothing). Fixtures in `frontend/src/test/catalogueApi.ts`
  gain `variants` in the data-model §2.5 shape with ui-spec §8 API-2's
  camelCase wire names, so 6.28 is a type swap.
- i18n: ui-spec §7's `admin.identity.variants.*` subtree +
  `catalogue.detail.trims.heading`.
- Tests via the `network.ts` dispatcher: the §3.2 **Test hooks** list, item
  by item — editor (add/edit/reorder/remove → save → panel resets clean;
  21st trim refused; duplicate name errors; used delta field disappears
  from the `Select`) in `ModelIdentityPanel.test.tsx`; customer (fixture
  with two trims, one with specs → two chips + one delta row; empty
  `variants` → no chips, no group) in `ModelSpecTable.test.tsx` and
  `CatalogueModelRoute.test.tsx`.

## Verification

- `pnpm lint`, `pnpm typecheck`, `make frontend-test` green (all §3
  test hooks covered).
- Dev-server smoke: the identity tab's trims editor renders and validates
  against a stubbed row; a live catalogue detail page (no `variants` on
  today's payload) is byte-identical to before this step.

## Risks / notes

- The a2Eligible delta input is a **yes/no `Select` with no "unknown"
  option** (§3.1) — an absent key already means "same as the base"; do not
  copy `ModelSpecsPanel`'s three-state idiom here.
- Reordering is `IconButton`s only — no drag-and-drop, no new dependency.
- Trim names/descriptions are verbatim, never translated (§7 exemption).
- Append (`### Step 6.25`) to `shared-knowledge.md`: the local
  catalogue-detail type extension 6.28 must delete, and the fixture shape.
