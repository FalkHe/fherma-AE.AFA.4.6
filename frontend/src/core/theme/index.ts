// Exports the theme and nothing else — no JSX, no provider (step-0.1.md
// §6.2, UI-43). `main.tsx` is the only place that renders `ThemeProvider`.
//
// Every colour/radius/shadow/easing value below is a `var(--…)` reference
// into the Goblin Pub design system's token files (`./tokens/*.css`,
// imported transitively through `./tokens.css`) — never a literal. The
// tokens are the single place a colour is written; this file only points at
// them. `frontend/src/structure.test.ts` (UI-34) enforces the literal ban
// for the whole `src` tree.
//
// Loading the CSS as the first statement guarantees the custom properties
// exist on `:root` before `createTheme` builds anything that references
// them via `var()` — MUI never resolves these itself (`nativeColor`, below),
// so order here does not matter for MUI, but it does for any other CSS the
// build pipeline concatenates.
import "./tokens.css";

import { createTheme, type Shadows } from "@mui/material/styles";
// `Theme.colorSchemes`/`defaultColorScheme` are only typed once this
// augmentation is imported somewhere in the program (MUI 9's opt-in for
// `cssVariables` typing) — otherwise they exist at runtime but `tsc`
// rejects reading them.
import type {} from "@mui/material/themeCssVarsAugmentation";

// The design system has one colour scheme: dark. `structure.test.ts`
// doesn't check this directly, but `docs/intents/007-initial-frontend`
// sprint 03's brief (AC2) requires only the dark scheme to exist — no
// `light` key at all, matching MUI's own documented pattern for a
// dark-only app (`colorSchemes: { dark: true }`).
declare module "@mui/material/styles" {
  interface Shape {
    borderRadiusOrganic: string;
    borderRadiusOrganicSoft: string;
    borderRadiusPill: string;
  }

  interface ShapeOptions {
    borderRadiusOrganic?: string;
    borderRadiusOrganicSoft?: string;
    borderRadiusPill?: string;
  }
}

// MUI elevations 0-24 (`theme.shadows`) collapse onto the design system's
// four shadow tiers (`--shadow-sm/md/lg/overlay`, `tokens/surfaces.css`).
// Elevation 0 is always "none" per MUI's contract; the rest step up through
// the tiers so higher elevations read as more lifted.
const shadows: Shadows = [
  "none",
  "var(--shadow-sm)",
  "var(--shadow-sm)",
  "var(--shadow-sm)",
  "var(--shadow-sm)",
  "var(--shadow-md)",
  "var(--shadow-md)",
  "var(--shadow-md)",
  "var(--shadow-md)",
  "var(--shadow-lg)",
  "var(--shadow-lg)",
  "var(--shadow-lg)",
  "var(--shadow-lg)",
  "var(--shadow-lg)",
  "var(--shadow-lg)",
  "var(--shadow-lg)",
  "var(--shadow-lg)",
  "var(--shadow-overlay)",
  "var(--shadow-overlay)",
  "var(--shadow-overlay)",
  "var(--shadow-overlay)",
  "var(--shadow-overlay)",
  "var(--shadow-overlay)",
  "var(--shadow-overlay)",
  "var(--shadow-overlay)",
];

export const theme = createTheme({
  // `nativeColor` lets every palette colour below be a bare `var(--…)`
  // string: MUI stops trying to parse it as an RGB/HSL literal and instead
  // emits it verbatim, computing `light`/`dark`/`contrastText` (where
  // omitted) with CSS `color-mix()` at paint time instead of Node-side
  // colour math. Confirmed present in the installed @mui/material@9.4.0
  // (docs pinned to v9.2.0 via context7 already document it; the package
  // changelog carries no removal between 9.2 and 9.4).
  cssVariables: { nativeColor: true },
  // Only the dark scheme exists — no `light` key. Without an explicit
  // `defaultColorScheme`, `createTheme` defaults it to `"light"` and then
  // (`createTheme.js`: `!palette && !("light" in colorSchemesInput) &&
  // defaultColorSchemeInput === "light"`) synthesises a stock-blue `light`
  // scheme just to satisfy that default — so it has to be pinned here, not
  // only via the `defaultMode="dark"` prop added to `ThemeProvider` in
  // `main.tsx`/`test/render.tsx` (which only picks the initial mode among
  // whatever schemes already exist).
  defaultColorScheme: "dark",
  colorSchemes: {
    dark: {
      palette: {
        primary: {
          main: "var(--accent)",
          light: "var(--accent-hover)",
          dark: "var(--accent-press)",
          contrastText: "var(--text-on-accent)",
        },
        secondary: {
          main: "var(--accent-secondary)",
        },
        error: {
          main: "var(--danger)",
        },
        warning: {
          main: "var(--warning)",
        },
        info: {
          main: "var(--info)",
        },
        success: {
          main: "var(--success)",
        },
        background: {
          default: "var(--surface-app)",
          paper: "var(--surface-card)",
        },
        text: {
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          disabled: "var(--text-faint)",
        },
        divider: "var(--border-soft)",
        action: {
          active: "var(--text-secondary)",
          hover: "var(--border-hairline)",
          selected: "var(--accent-quiet)",
          disabled: "var(--text-faint)",
          disabledBackground: "var(--border-hairline)",
          focus: "var(--accent-quiet)",
        },
      },
    },
  },
  typography: {
    fontFamily: "var(--font-body)",
    h1: {
      fontFamily: "var(--font-display)",
      fontWeight: "var(--weight-bold)",
      fontSize: "var(--text-display)",
      lineHeight: "var(--lh-display)",
      letterSpacing: "var(--ls-display)",
    },
    h2: {
      fontFamily: "var(--font-display)",
      fontWeight: "var(--weight-bold)",
      fontSize: "var(--text-h1)",
      lineHeight: "var(--lh-h1)",
      letterSpacing: "var(--ls-h1)",
    },
    h3: {
      fontFamily: "var(--font-display)",
      fontWeight: "var(--weight-bold)",
      fontSize: "var(--text-h2)",
      lineHeight: "var(--lh-h2)",
    },
    h4: {
      fontFamily: "var(--font-display)",
      fontWeight: "var(--weight-bold)",
      fontSize: "var(--text-h3)",
      lineHeight: "var(--lh-h3)",
    },
    h5: {
      fontFamily: "var(--font-body)",
      fontWeight: "var(--weight-medium)",
      fontSize: "var(--text-lead)",
      lineHeight: "var(--lh-lead)",
    },
    h6: {
      fontFamily: "var(--font-body)",
      fontWeight: "var(--weight-bold)",
      fontSize: "var(--text-body)",
      lineHeight: "var(--lh-body)",
    },
    subtitle1: {
      fontFamily: "var(--font-body)",
      fontWeight: "var(--weight-medium)",
      fontSize: "var(--text-lead)",
      lineHeight: "var(--lh-lead)",
    },
    subtitle2: {
      fontFamily: "var(--font-body)",
      fontWeight: "var(--weight-medium)",
      fontSize: "var(--text-body)",
      lineHeight: "var(--lh-body)",
    },
    body1: {
      fontFamily: "var(--font-body)",
      fontWeight: "var(--weight-regular)",
      fontSize: "var(--text-body)",
      lineHeight: "var(--lh-body)",
    },
    body2: {
      fontFamily: "var(--font-body)",
      fontWeight: "var(--weight-regular)",
      fontSize: "var(--text-small)",
      lineHeight: "var(--lh-small)",
    },
    caption: {
      fontFamily: "var(--font-body)",
      fontWeight: "var(--weight-regular)",
      fontSize: "var(--text-micro)",
      lineHeight: "var(--lh-micro)",
    },
    overline: {
      fontFamily: "var(--font-body)",
      fontWeight: "var(--weight-medium)",
      fontSize: "var(--text-micro)",
      lineHeight: "var(--lh-micro)",
      letterSpacing: "var(--ls-label)",
      textTransform: "uppercase",
    },
    button: {
      fontFamily: "var(--font-body)",
      fontWeight: "var(--weight-medium)",
      fontSize: "var(--text-small)",
      lineHeight: "var(--lh-small)",
      letterSpacing: "var(--ls-label)",
      textTransform: "none",
    },
  },
  // `tokens/spacing.css`'s `--sp-0`..`--sp-12` scale (0, 2, 4, 8, 12, 16, 20,
  // 24, 32, 40, 56, 72, 96px). `theme.spacing(n)` must return a length MUI
  // can arithmetic on, so — unlike colour — this is the one axis where the
  // token's *pixel numbers* are copied in rather than referenced by
  // `var()`; there is no colour here for UI-34 to police.
  spacing: [0, 2, 4, 8, 12, 16, 20, 24, 32, 40, 56, 72, 96],
  shape: {
    // `--radius-sm` (10px, `tokens/surfaces.css`) backs the numeric
    // `borderRadius` every stock MUI component multiplies internally; it
    // must stay a plain number for that arithmetic; MUI-9.4's own contract
    // for the non-standard radii is that they live outside it.
    borderRadius: 10,
    // The organic, non-uniform radii (WI1's tested behaviour): each corner
    // differs, which a plain `borderRadius: number` can't express, so they
    // are carried as their own theme keys (augmented above) instead of
    // overloading the standard one.
    borderRadiusOrganic: "var(--radius-organic)",
    borderRadiusOrganicSoft: "var(--radius-organic-soft)",
    borderRadiusPill: "var(--radius-pill)",
  },
  shadows,
  transitions: {
    easing: {
      easeInOut: "var(--ease-standard)",
      easeOut: "var(--ease-out-soft)",
      easeIn: "var(--ease-in)",
      sharp: "var(--ease-standard)",
    },
    // Durations stay numeric (milliseconds) — MUI appends `ms` to build the
    // CSS `transition` string, so a `var()` here would emit invalid CSS
    // (`var(--dur-fast)ms`). Values are read from the token *values*
    // (`tokens/motion.css`: 90/150/220/400ms), not from
    // `_ds_manifest.json`, which reports the `prefers-reduced-motion`
    // override (`--dur-fast: 0ms`) instead of the base duration — see the
    // sprint brief's trap note.
    duration: {
      shortest: 90,
      shorter: 150,
      short: 150,
      standard: 220,
      complex: 400,
      enteringScreen: 220,
      leavingScreen: 150,
    },
  },
});
