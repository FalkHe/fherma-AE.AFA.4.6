---
phase: 5
step: "5.12"
title: Shared UntrustedMarkdown renderer + chat inertness test
summary: Consolidate the three duplicated react-markdown configs into UntrustedMarkdown.tsx (raw HTML off always, no plugin props exposed), re-point MessageBubble / CatalogueModelRoute / ModelDocumentsPanel with byte-identical rendering, and add the missing MessageBubble raw-HTML inertness test.
effort: 2
dependencies: []
---

# Step 5.12 — Shared `UntrustedMarkdown` renderer + chat inertness test

**Effort: 2** — a consolidation refactor against a fully specified component
API, plus one test file. The rule of three is now reached (three duplicated
sites), so the consolidation deferred in Phases 3/4 is due.

Binding contract: `docs/roadmap/phase-5/shared-knowledge.md` (D9) and
**`docs/roadmap/phase-5/ui-spec.md` §4** (the component API, base-sx
intersection, per-site migration notes and §4.4 tests are the truth — this
file only sequences). Agent: **frontend-dev**. Zero deviations — a deviation
is a stop-and-report.

**Environment:** no backend needed; `make frontend-test` / `pnpm test` run
without the stack.

## Outline

- New `frontend/src/components/UntrustedMarkdown.tsx` per ui-spec §4.2:
  raw HTML off (never `rehype-raw` — no plugin props exposed, so no call
  site can ever add it), `remark-gfm`, the shared `ExternalLink`
  (`target="_blank" rel="noopener noreferrer"`), base sx = the exact
  intersection of the three landed `MARKDOWN_SX` variants.
- Re-point the three sites per ui-spec §4.3, keeping their deltas
  module-local (CatalogueModelRoute keeps heading demotion + `ProseTable`
  overflow wrapper; MessageBubble rendering stays byte-identical — user
  messages remain plain text, never markdown).
- New `UntrustedMarkdown.test.tsx` per ui-spec §4.4, **plus** the missing
  MessageBubble inertness case (`<script>`/`<img onerror>` in an assistant
  body render as inert text — the catalogue/admin-review equivalents already
  exist and must stay green).

## Verification

- `pnpm lint && pnpm typecheck && pnpm test` green (or `make frontend-*`).
- Visual spot-check on the running app: chat assistant markdown, catalogue
  article (incl. wide GFM table still scrolling in its wrapper), admin
  document view — all unchanged.

## Risks / notes

- Byte-identical rendering is the contract — if a delta can't stay local
  without changing output, stop and report.
- `react-refresh/only-export-components`: `ExternalLink` lives inside the
  component file only if it isn't co-exported; follow ui-spec §4.2's layout.
- Append (`### Step 5.12`) to `shared-knowledge.md`: the final prop surface
  — 5.13 and any later markdown surface build on it.
