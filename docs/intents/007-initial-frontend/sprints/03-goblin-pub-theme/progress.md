---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: draft
---
# Progress: Sprint 03

| WI | Status | Note |
|---|---|---|
| 1 | done | Token CSS copied verbatim into `core/theme/tokens/`; dark-only theme in CSS-variable mode. `defaultColorScheme: "dark"` inside `createTheme` was required — `defaultMode` on the provider alone still let MUI synthesize a stock-blue light scheme (the gap qa caught) |
| 2 | done | Five pinned deps installed, lockfile clean, typecheck green. `@fontsource-variable` registers faces as "<Family> Variable", so `fonts.css` adds two Latin-range `@font-face` aliases to make the verbatim family names in `typography.css` resolve — still fully self-hosted, `typography.css` untouched |
| 3 | done | Name changed through the existing `common:app.title` key plus the tab title and two test literals; lint clean |
| 4 | running | |
| 5 | running | |
| qa | done | 2 acceptance tests: AC4 green; AC2 red on a real theme gap — `createTheme` without `defaultColorScheme: "dark"` makes MUI inject a light scheme (`frontend/src/core/theme.test.ts`, `frontend/src/productName.test.tsx`) |

Status: `open | running | done | failed`

## Issues
- Research raised three finish questions as product-visible; decided rather than escalated, since the brief's own assumptions already govern them: fonts are self-hosted rather than loaded from a font CDN, the name uses a plain apostrophe, and the wordmark is set in the display face.
- The frontend container's `node_modules` needs `make rebuild` after WI2's dependency change before any suite run (`ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`).
- No browser acceptance suite exists in this project and the brief does not ask for one; acceptance is covered by the unit-level suite plus a live look at the running app.

## Backlog proposals
- The interactive API page still calls the product by its old name: that title comes from the backend, which this sprint may not touch. One small backend change would finish the rename.

## Verify
