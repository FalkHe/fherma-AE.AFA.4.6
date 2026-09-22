---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 03

## Work items
| WI | Agent | Deliverable | Behaviours | Depends on |
|---|---|---|---|---|
| 1 | ui-designer | The design system's token files ship in the frontend and the theme is built from them, one scheme only, no colour written elsewhere | One scheme; palette, radius, shadow and transition values read back as token references; organic radii are theme values | – |
| 2 | frontend | The four design faces load without a third-party request; a Lucide icon package is available | Families resolve from local packages; an icon imports and typechecks | – |
| 3 | frontend | Everywhere the product named itself it reads "The Goblin's Tavern" | Tab title and wordmark on all three screens; the old name occurs nowhere | – |
| 4 | frontend | The structure test states the new pinned files and allowed icon package, with reasons | An unpinned file under core, or a colour literal in a stylesheet outside the token directory, fails it | 1, 2 |
| 5 | ui-designer | The three screens render in the dark palette, type and uneven corners, behaving as before | Every existing auth, home and shell test passes; no colour or radius literal in a component | 1, 3 |
| qa | qa | Acceptance tests for the criteria | below | – |

## Interfaces
- I1 — WI1 owns `frontend/src/core/theme/`: creates `tokens/{base,colors,motion,spacing,surfaces,typography}.css` (verbatim bundle copies), `tokens.css` (the bundle's `styles.css`, importing all seven token files under the same names) and `index.ts`; deletes `core/theme.ts`. `index.ts` begins `import "./tokens.css";` and keeps the export name `theme`, so `"./core/theme"` (`main.tsx:18`) and `"../core/theme"` (`test/render.tsx:15`) still resolve — no import site is edited. It augments `Shape`/`ShapeOptions` of `@mui/material/styles` with three `string` keys `borderRadiusOrganic`, `borderRadiusOrganicSoft`, `borderRadiusPill` (optional in `ShapeOptions`), set to `var(--radius-organic)`, `var(--radius-organic-soft)`, `var(--radius-pill)`.
- I2 — WI2 owns `frontend/package.json` and `frontend/src/core/theme/tokens/fonts.css` alone. `fonts.css`, the one file not copied verbatim, imports the `@fontsource` stylesheets instead of Google Fonts, leaving the families in `tokens/typography.css` as shipped. Adds to `dependencies` exactly: `"lucide-react": "^1.47.0"`, `"@fontsource-variable/alegreya": "^5.3.0"`, `"@fontsource/alegreya-sans": "^5.3.0"`, `"@fontsource/alegreya-sc": "^5.3.0"`, `"@fontsource-variable/jetbrains-mono": "^5.3.0"`.
- I3 — WI3 changes only the value of `app.title` in `core/i18n/locales/en/common.json` to `The Goblin's Tavern` (ASCII apostrophe), plus the untranslated copies at `frontend/index.html:6`, `src/App.test.tsx:53`, `src/modules/home/routes/HomeRoute.test.tsx:15`. No new key — every call site already reads it.
- I4 — WI4 changes only `frontend/src/structure.test.ts`. WI5 changes only `AppShell.tsx`, `AuthCard.tsx` and the three route files, and reads radii only through `theme.shape`.

## Acceptance tests (qa)
- AC2 → the theme has a dark scheme and no light one, and its primary colour is not the stock library blue.
- AC4 → each screen shows "The Goblin's Tavern", and so does the tab title.
- AC3 → the existing suite stays green.
- AC1/AC5 → the structure test (WI4); qa does not duplicate it.

## Order
Parallel: WI1, WI2, WI3, qa. Then, after a dependency install: WI4, WI5.
