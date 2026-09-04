---
phase: 2
step: "2.2"
title: Phase-2 admin UI spec
summary: Binding layout/state/i18n-key specification for the backlog list, add-model dialog, live progress treatment, and the three-tab review screen — mirrors the Phase-1 ui-spec format.
effort: 2
dependencies: []
agent: ui-ux-designer
track: frontend
---

# Step 2.2 — Phase-2 admin UI spec

**Status: ✅ complete** — [`ui-spec.md`](ui-spec.md) landed 2026-08-26 and was
reconciled against [`shared-knowledge.md`](shared-knowledge.md) (hook file
split, separate documents/images endpoints, pinned price-band/category
vocabularies). This step file is retained for numbering and provenance.

## Deliverable

`docs/roadmap/stage-01/phase-2/ui-spec.md`, binding for frontend steps 2.8, 2.13,
2.15, 2.20. Key decisions recorded there:

- No second admin tab — review is a drill-down at `/admin/models/:motorbikeId`.
- `OperationProgress` is the graded live-progress element; SSE disconnect
  warning in `AdminLayout` after a 5 s grace period; no polling anywhere.
- No optimistic updates — every mutation awaits the server and invalidates.
- Retry/start ingestion = `PATCH` status → `ingesting` (no action endpoints).
- RHF + Zod only for the draft-spec review form; plain controlled inputs
  everywhere else.
- Admins edit the **draft** spec only; approval promotes; the UI never
  writes `verified`.
