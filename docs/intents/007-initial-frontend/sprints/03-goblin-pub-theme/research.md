---
author: fhit:architect
owner: agent
created: 2026-09-22
---
# Research: 007 Sprint 03 — Goblin Pub theme

## Facts

**Theme today.** `frontend/src/core/theme.ts:5-8` is the whole theme —
`createTheme({ cssVariables: true, colorSchemes: { light: true, dark: true } })`: stock MUI blue, both
schemes. Mounted at `main.tsx:24-33`, mirrored for tests at `test/render.tsx:29-37`. No `sx` colour
literal exists anywhere.

**What the bundle ships.** Tokens only — the readme's `mui/goblinPubTheme.js`, `components/` and
`ui_kits/` are **not in the handoff**. Under
`docs/design/dnd-app-dashboard-design/project/_ds/goblin-pub-design-system-dfb40ce4-5a9b-4ace-851e-34d13fec04a1/`:
`styles.css` (7 `@import`s) and `tokens/{fonts,colors,typography,spacing,surfaces,motion,base}.css` —
plain custom properties on `:root`, no build step, copyable verbatim. Ramps `colors.css:3-30`, aliases
`:32-68` (`--surface-app`, `--accent`, `--focus-ring`, …); radii `surfaces.css:3-6` incl.
`--radius-organic:22px 16px 24px 18px`; shadows `:11-17`; motion `motion.css:2-10`; `base.css:1` sets
`color-scheme:dark`. Trap: `_ds_manifest.json` reports `--dur-fast: 0ms`, having captured the
`prefers-reduced-motion` override (`motion.css:13-17`); real values are 150/220/400 ms.

**Fonts.** `tokens/fonts.css:3` is one `@import url("https://fonts.googleapis.com/css2?…")` for Alegreya,
Alegreya SC, Alegreya Sans, JetBrains Mono — Google Fonts substitutes the readme says "can be
self-hosted". All four are on npm: `@fontsource-variable/alegreya`, `@fontsource/alegreya-sans`,
`@fontsource/alegreya-sc`, `@fontsource-variable/jetbrains-mono`, each 5.3.0 (source: npm registry; no
variable Alegreya Sans exists). None installed.

**Icons.** The readme substitutes Lucide (`lucide-static@0.469.0`, unpkg); the prototypes use `beer,
book-open, chevron-left, feather, flame, footprints, lock, log-out, plus, shield`. For this stack:
`lucide-react@1.47.0` — ISC, no runtime deps, `peerDependencies.react "^19.0.0"` (installed 19.2.8),
`typings: dist/lucide-react.d.ts`, `sideEffects: false` (source: npm registry). Not installed.

**Structure test.** `structure.test.ts:73-88` (UI-33) asserts per dependency
`expect(name).not.toMatch(/icons?-material/i)` and per `.ts(x)` file `not.toMatch(/@mui\/icons-material/)`.
`lucide-react` matches neither, so the **assertions pass unchanged**; only the test's claim is false —
`"UI-33: no icon package is a dependency, and no component imports one"`. UI-34 (`:90-97`) scans only
`` /\.(ts|tsx|json)$/ `` for `` /#[0-9a-fA-F]{3,8}\b|(?:rgb|hsl)a?\(/ `` — `.css` is outside its scan, so
CSS token files satisfy AC1 with the rule untouched. UI-43 (`:109-127`) pins `core/` to an exact
nine-entry list including `theme.ts` and forbids `.tsx` there.

**Product name.** One key: `common:app.title` = `"AI Dungeon Master"`
(`frontend/src/core/i18n/locales/en/common.json:3`), read at `AuthCard.tsx:35`, `HomeRoute.tsx:24,35`,
`SignInRoute.tsx:22`, `SignUpRoute.tsx:16`; non-i18n copies at `frontend/index.html:6`, `App.test.tsx:53`
and `HomeRoute.test.tsx:15`. Locales: English only, namespaces `common`, `auth`, `home`
(`core/i18n/index.ts:10-12`).

`frontend/vitest.config.ts:13` sets `css: false`, so token CSS never evaluates under Vitest: no assertion
can observe the palette, and those two literals are the only forced test edits (AC3).

## Work items

- **WI1 — tokens + dark-only theme.** The frontend source carries the design system's token files and a
  theme built from them, with one colour scheme and no colour value outside the tokens. Checks: one scheme
  only; palette, radius and transition values read back as `var(--…)`.
- **WI2 — fonts and icon package.** The four faces load without a third-party request and a Lucide icon
  package is installable. Checks: families resolve locally; `lucide-react` imports and typechecks. Owns
  `package.json` alone.
- **WI3 — the product is called The Goblin's Tavern.** Every place the old name appeared reads the new
  one, through the existing translation key. Checks: tab title and wordmark on all three screens; the old
  name occurs nowhere under `frontend/`.
- **WI4 — structure test states the new facts.** The pinned list covers the token files and the test says
  which icon package is allowed and why. Checks: an unpinned file under `core/`, or a colour literal
  outside the token directory, fails it. After WI1, WI2 (names fixed below).
- **WI5 — the three screens on the new look.** Sign-in, sign-up and the landing screen render in the dark
  palette and type with the uneven panel corners, behaving exactly as before. Checks: every existing
  auth/home/App test passes apart from the name; no colour or radius literal in a component. After WI1, WI3.

WI1–WI3 run in parallel; WI4 and WI5 follow WI1 on disjoint files.

## Interfaces

**WI1 creates**, verbatim copies of the bundle:
`frontend/src/core/theme/tokens/{colors,typography,spacing,surfaces,motion,base}.css`,
`frontend/src/core/theme/tokens.css` (the bundle's `styles.css`, `@import`ing all seven token files under
the same names), `frontend/src/core/theme/index.ts`. `core/theme.ts` is deleted; the directory resolves
for the existing specifiers `"./core/theme"` (`main.tsx:18`) and `"../core/theme"` (`test/render.tsx:15`)
— **no import site changes**.

`core/theme/index.ts`: first statement `import "./tokens.css";`, then `export const theme` (same name),
built as `createTheme({ cssVariables: { nativeColor: true }, colorSchemes: { dark: { palette: … } }, … })`.
`nativeColor` permits `palette.primary.main: "var(--accent)"` without MUI parsing the value
(@mui/material 9.4.0 — source: context7, v9.2.0 `css-theme-variables/native-color`); modern browsers only.
The same file augments `Shape` and `ShapeOptions` of `@mui/material/styles` with three `string` keys
(optional in `ShapeOptions`): `borderRadiusOrganic`, `borderRadiusOrganicSoft`, `borderRadiusPill`, set to
`"var(--radius-organic)"`, `"var(--radius-organic-soft)"`, `"var(--radius-pill)"`. WI5 reads radii only
through `theme.shape`, never as a literal.

**WI2 creates** `frontend/src/core/theme/tokens/fonts.css` — the one token file not copied verbatim: it
`@import`s the `@fontsource` CSS instead of Google Fonts — and adds to `frontend/package.json`
`dependencies`, exactly: `"lucide-react": "^1.47.0"` plus the four `@fontsource` packages named above at
`"^5.3.0"`. Nothing else; the family names in `tokens/typography.css:2-5` stay as shipped, so WI1 and WI2
cannot disagree.

**WI3 changes** only `app.title` in `frontend/src/core/i18n/locales/en/common.json` to
`The Goblin's Tavern` (ASCII apostrophe), plus `frontend/index.html:6`, `frontend/src/App.test.tsx:53`
and `frontend/src/modules/home/routes/HomeRoute.test.tsx:15`. **No new key, no new namespace** — every
call site already reads `common:app.title`.

**WI4 changes** only `frontend/src/structure.test.ts`: in the UI-43 array (`:111-121`) `"theme.ts"`
becomes `"theme/index.ts"`, `"theme/tokens.css"` and `"theme/tokens/{base,colors,fonts,motion,spacing,
surfaces,typography}.css"` — 17 entries, the other 8 untouched. UI-33's title and comment become "the only
icon package is `lucide-react`; `@mui/icons-material` stays forbidden", keeping both assertions plus an
explicit allow-list check, and one new case asserting no `.css` outside `src/core/theme/tokens/` holds a
colour literal. UI-34 is untouched.

**WI5 changes** `AppShell.tsx`, `AuthCard.tsx` and the three route files only.

## Open questions

**Product-visible:**
- Fonts self-hosted (recommended: no third-party request, works offline and under a strict CSP) versus the
  bundle's Google Fonts import, where a blocked CDN falls back to Georgia / system-ui. D11 leaves this to
  the agent, so self-hosting proceeds as an assumption unless vetoed.
- The apostrophe: assumed ASCII `The Goblin's Tavern`, not the typographic `’`.
- The wordmark is assumed set in the display small-caps face, not the sans.

**Internal (agent's call):** whether `colorSchemes: { dark: true }` alone suffices or `defaultMode="dark"`
must also reach both `ThemeProvider`s; `nativeColor` versus explicit `main`/`light`/`dark`/`contrastText`
`var()` values per colour (the fallback if MUI parses a value); whether `@fontsource/alegreya-sc` ships
now or with the first small-caps label.
