---
phase: 4
step: "4.6"
title: Phase-4 UI spec (catalogue list, filters, model detail)
summary: The binding UI specification for the two customer catalogue pages — layout, MUI components, URL-param filter behaviour, spec-table grouping, states, i18n keys, a11y — produced by the ui-ux-designer and reconciled by the PM.
effort: 2
dependencies: []
---

# Step 4.6 — Phase-4 UI spec

**Effort: 2** — a specification step, no code. **Executed at slicing time
(2026-08-28)** by the ui-ux-designer; the deliverable is
[`ui-spec.md`](ui-spec.md), reconciled with the architect's API contract by
the PM (the Phase-3 precedent: spec steps run during planning so the
frontend track starts unblocked).

## Outline

- `docs/roadmap/stage-01/phase-4/ui-spec.md` following the Phase-3 ui-spec
  structure: route & file map, shared building blocks, CatalogueRoute
  (grid, filter panel incl. exact `useSearchParams` handling, pagination),
  CatalogueModelRoute (gallery, grouped 13-field spec table, article
  prose, sources block), states matrix (loading / empty / no-match / error
  / 404 / image-less), app-shell integration (nav entry), i18n key list,
  accessibility checklist.
- Open points it cannot decide from the frontend alone are listed at its
  end and resolved by the PM against `shared-knowledge.md` (a
  "Resolutions" section, the Phase-3 §14 precedent).

## Verification

- `ui-spec.md` exists, carries no unresolved DRAFT markers, and answers at
  minimum: mobile filter presentation (drawer vs inline), card hierarchy,
  spec-table grouping of the 13 frozen fields, filter
  apply-on-change-vs-button behaviour, the empty/no-match/404 states, and
  the i18n keys — precise enough that 4.7/4.8 raise zero questions.

## Risks / notes

- Where the ui-spec and `shared-knowledge.md` disagree, shared-knowledge
  wins (standing rule); report the conflict rather than building either
  version.
