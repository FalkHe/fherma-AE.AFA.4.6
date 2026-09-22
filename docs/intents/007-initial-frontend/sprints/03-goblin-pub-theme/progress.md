---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: done
---
# Progress: Sprint 03

| WI | Status | Note |
|---|---|---|
| 1 | done | Token CSS copied verbatim into `core/theme/tokens/`; dark-only theme in CSS-variable mode. `defaultColorScheme: "dark"` inside `createTheme` was required — `defaultMode` on the provider alone still let MUI synthesize a stock-blue light scheme (the gap qa caught) |
| 2 | done | Five pinned deps installed, lockfile clean, typecheck green. `@fontsource-variable` registers faces as "<Family> Variable", so `fonts.css` adds two Latin-range `@font-face` aliases to make the verbatim family names in `typography.css` resolve — still fully self-hosted, `typography.css` untouched |
| 3 | done | Name changed through the existing `common:app.title` key plus the tab title and two test literals; lint clean |
| 4 | done | UI-43 repinned to the real tree; UI-33's claim restated with a lucide-react allow-list guard; new case bars colour literals in any stylesheet outside the token directory; UI-34 untouched. Both new guards probe-verified |
| 5 | done | `AppShell`, `AuthCard` and `HomeRoute` restyled through `theme` and `theme.shape` only; the two route files needed no change. Confirmed live at 1280×800 and 390×844 |
| qa | done | 2 acceptance tests: AC4 green; AC2 red on a real theme gap — `createTheme` without `defaultColorScheme: "dark"` makes MUI inject a light scheme (`frontend/src/core/theme.test.ts`, `frontend/src/productName.test.tsx`) |

Status: `open | running | done | failed`

## Issues
- Research raised three finish questions as product-visible; decided rather than escalated, since the brief's own assumptions already govern them: fonts are self-hosted rather than loaded from a font CDN, the name uses a plain apostrophe, and the wordmark is set in the display face.
- The frontend container's `node_modules` needs `make rebuild` after WI2's dependency change before any suite run (`ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`).
- No browser acceptance suite exists in this project and the brief does not ask for one; acceptance is covered by the unit-level suite plus a live look at the running app.

## Backlog proposals
- The icon package is installed and allow-listed but nothing imports it yet: the three screens carry no icons. It is there for the screens the next sprints build.
- The sign-out control's focus indicator is a faint fill rather than the design's crisp ring; the header and its account menu are rebuilt next sprint, which is where this belongs.
- The interactive API page still calls the product by its old name: that title comes from the backend, which this sprint may not touch. One small backend change would finish the rename.

## Verify
Round 1: approve, no failed criteria. All five criteria checked live in the browser. The merge request
could not be approved by button — the reviewing account authored it, so GitLab refuses self-approval; the
verdict is posted as a note instead (note_437). Human approval on the MR is still outstanding.
