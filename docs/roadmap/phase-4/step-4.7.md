---
phase: 4
step: "4.7"
title: Catalogue list page on stubs
summary: CatalogueRoute at /catalogue — responsive card grid, the URL-persisted filter panel (useSearchParams as the single source of truth), server-driven pagination, nav entry — built entirely against stub hooks, zero backend code.
effort: 4
dependencies: ["4.6"]
---

# Step 4.7 — Catalogue list page on stubs

**Effort: 4** — the biggest frontend slice: grid + filter panel + URL-state
discipline + pagination + states, all on fixture data.

Binding contracts: `docs/roadmap/phase-4/ui-spec.md` (layout truth) and
`docs/roadmap/phase-4/shared-knowledge.md` (*Frontend conventions — delta*;
URL-param pins, hook exports, queryKeys). Conventions: Phase-1/2/3
shared-knowledge frontend sections. Agent: **frontend-dev**. Needs **zero
backend code**. Zero deviations — a deviation is a stop-and-report.

## Outline

- `frontend/src/hooks/useCatalogueModels.ts` — **stub** (clearly marked,
  the Phase-1 stub rule: real `useQuery` results over fixture data, exact
  pinned export names/types so 4.9 deletes the file wholesale):
  `useCatalogueModels(filters)`, `useManufacturers()` + types
  `CatalogueListItem`, `Manufacturer`. Fixture requirements are **binding**
  in ui-spec §8 (≥ `PAGE_SIZE + 3` items; the stub filters/sorts/pages the
  fixture array from the parsed URL params).
- `frontend/src/hooks/useCatalogueFilters.ts` — `useCatalogueFilters()`
  (parse/normalize/write helpers, active-filter count) +
  `parseCatalogueFilters` per ui-spec §3.2/§3.3. **Never a stub** — pure
  URL logic, survives 4.9. SPA param names exactly per ui-spec §3.2;
  defaults omitted from the URL; any filter/sort change deletes `page`.
- `frontend/src/routes/CatalogueRoute.tsx` at `/catalogue` (route table in
  `App.tsx`, under `RequireAuth`): layout per ui-spec §3.1 — desktop
  sidebar + mobile filter `Drawer` (§3.6), toolbar with result count +
  sort select, responsive card grid of `CatalogueModelCard` (§3.5: image
  `srcSet` thumb/card + `loading="lazy"`, image-less fallback, name,
  manufacturer · category, price-band chip, headline specs — nulls
  omitted), whole card surface linking to `/catalogue/:motorbikeId`.
- `frontend/src/components/CatalogueFilters.tsx` — every control bound to
  `useSearchParams` via `useCatalogueFilters` **only** (no duplicate local
  state). Full filter set per ui-spec §3.4 (manufacturer, category,
  priceBand, cc min/max, kW min/max, seat max, weight max, A2-only).
  Apply behaviour exactly per §3.4: selects/checkbox apply immediately;
  number fields commit on blur/Enter (uncontrolled, `key`-remounted).
- `PAGE_SIZE = 24` module constant; MUI `Pagination` bound to the `page`
  param (server-driven — not the admin walk-all-pages pattern);
  `keepPreviousData` + the reserved `LinearProgress` slot on refetch.
- States per ui-spec §3.7: 8 skeleton cards (no layout jump), empty
  catalogue (advisor CTA), no-filter-match with clear-filters affordance,
  error with retry.
- `specFields.ts` gains `formatSpecEnum`; **R9 hoist** (ui-spec §2.1):
  `admin.review.specs.categoryValues`/`priceBandValues` move verbatim to
  `common.specEnums.*` and the admin spec form is re-pointed — the one
  admin file this step touches.
- App shell: `nav.catalogue` entry in `AppLayout` per ui-spec §7 (incl.
  the xs title-hiding tweak); `queryKeys.ts` gains
  `catalogue.{list(filters), detail(id)}` + `manufacturers.list()`; i18n
  `catalogue.*` keys per ui-spec §9. Do **not** touch
  `useServerEvents.ts` here (4.9).

## Verification

- `make frontend-test` + `pnpm lint` + `pnpm typecheck` green; tests: a
  filter change updates the URL and the query key; reload (re-mount with
  the same URL) reproduces filter state; empty/no-match states render;
  pagination updates `page`.
- In the browser (stack up, stub data): set filters → reload → filters and
  results unchanged; URL shareable.

## Risks / notes

- Do not touch `useServerEvents.ts` invalidations here — that lands in 4.9
  with the real hooks (stub data has nothing to invalidate).
- Append UI-contract decisions 4.8/4.9 depend on (`### Step 4.7`) to
  `shared-knowledge.md`.
