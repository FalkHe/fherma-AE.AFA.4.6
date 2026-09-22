---
author: fhit:architect
owner: human
created: 2026-09-22
stage: draft
---
# Sprint 03: Goblin Pub theme

## Task
Adopt the delivered design system: bring its colour, type, spacing, radius, surface and motion tokens into the
frontend, drive the theme from them as a dark-only scheme, load the display, sans and mono faces, and settle how the
design's icons are represented without adding an icon package. Rename the product to "The Goblin's Tavern" and
re-render the existing sign-in, sign-up and landing screens on it, relaxing the pinned structure test to admit the new
files.

## Outcome
Sign-in, sign-up and the landing page render in the design's dark palette and type with the product named "The
Goblin's Tavern", there is no light mode, and no screen still shows the stock blue.

## Acceptance criteria
- AC1: The design system's token files ship inside the frontend source and are the only place a colour value is
  written; the "no colour literal" structure rule still passes unchanged (← D14).
- AC2: The theme is built from those tokens — palette, typography, spacing, radii, shadows, transitions — and only
  the dark scheme exists (← D11, D14).
- AC3: The three existing screens behave exactly as before; the whole existing frontend suite still passes.
- AC4: The product name reads "The Goblin's Tavern" wherever it appeared, through translation keys (← D14).
- AC5: Lint, typecheck and tests pass, and `frontend/src/structure.test.ts` states the new pinned file list with
  its reason.

## Decisions
← D11, D14

## Assumptions
- The design bundle's compiled React components are **not** consumed — only its tokens, themed through component
  overrides on the UI library already in the stack (the handoff ships no theme file, so it is authored from the
  tokens).
- Fonts follow the design system's own loading note; icons are inline in-repo marks, since an icon package is
  forbidden.
- The uneven "organic" radii are expressed as theme values, not per-component literals.

## Out of scope
No new screen or route · no backend · no light mode · nothing from the play/session view.
