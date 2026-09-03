---
phase: 3
step: "3.10"
title: Tool renderers, sources & recommendation cards, UI-only
summary: The grading-critical message parts as pure presentational components — four labelled tool-result renderers plus generic fallback and subtle rows, the collapsible sources section, and recommendation cards — proven against fixture props.
effort: 4
dependencies: ["3.2", "3.6"]
---

# Step 3.10 — Tool renderers, sources & recommendation cards, UI-only

**Effort: 4** — seven components and their fixture-driven tests; zero
backend code, **no stub hooks** (the hooks are real since 3.6; these are
pure components fed typed props, so 3.15 changes nothing here).

Binding contracts: `docs/roadmap/phase-3/ui-spec.md` (§6 part order,
§7–§9, §11–§13) and `docs/roadmap/phase-3/shared-knowledge.md` (§Persisted
JSONB shapes, §Tool result schemas — the fixture data MUST match these
pinned shapes exactly). Agent: **frontend-dev**.

## Outline

- Components flat in `frontend/src/components/` (ui-spec §1 overrules any
  subdirectory idea): `ToolResultBlock.tsx` (frame + dispatcher + generic
  fallback §8.6 + subtle rows §8.7), `ToolResultCatalogueSearch.tsx`,
  `ToolResultSpecComparison.tsx` (horizontal scroll inside the bubble),
  `ToolResultLicenceFitCheck.tsx` (verdict chips + verbatim evidence),
  `ToolResultCostEstimator.tsx` (always-visible Estimate chip + collapsible
  assumptions), `MessageSources.tsx` (§7), `RecommendationCard.tsx` (§9 —
  non-interactive, `motorbikeId` prop reserved for Phase 4's link;
  `imageUrl` prefixed with `VITE_API_URL`, thumb derived by variant-suffix
  replacement).
- Integrate into `MessageBubble`'s part slots in the pinned order: tool
  blocks → markdown body → recommendation cards → sources toggle.
- Shape-check dispatch: a result the renderer cannot parse falls back to
  the generic renderer — a shape check, not a try/catch around render.
- Extend `consultations.specFields.*` to all frozen spec field names
  (comparison rows are keyed by them); unmapped keys render verbatim.
- Tests: every renderer from fixtures matching the pinned schemas (ui-spec
  §12 kitchen-sink message: all four tools, one unknown tool, subtle rows,
  source de-dup, null-image card, nulls → em dashes), collapsed/expanded
  toggles, i18n keys present.

## Verification

- `make frontend-test` + lint + typecheck green; the kitchen-sink fixture
  message renders all four labelled tool blocks, the generic fallback, both
  subtle rows, a de-duplicated sources list, and two cards (one image
  fallback). **This closes milestone M3's frontend half.**

## Risks / notes

- Fixture shapes are the contract test for 3.13's persisted output — if a
  pinned shape seems unworkable while building, stop and report; do not
  bend the fixture.
