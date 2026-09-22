// Acceptance test for sprint 007/03 "Goblin Pub theme" AC2. `css: false` in
// vitest.config.ts means the token stylesheets never evaluate here, so
// rendered colours are not observable — this asserts on the exported theme
// object itself (plan.md I1), which is what the brief's "only the dark
// scheme exists" and "not the stock blue" claims are actually made of.
//
// Import path deliberately mirrors the one contract-fixed site
// (`test/render.tsx`'s `"../core/theme"`) one directory shallower, so it
// keeps resolving whether `theme` still lives at `core/theme.ts` or has
// moved to `core/theme/index.ts` (plan.md I1) without this file caring which.
import { describe, expect, it } from "vitest";

import { theme } from "./theme";

const STOCK_MUI_BLUE = "#1976d2";

describe("core/theme", () => {
  it("AC2: is dark-only, and no colour scheme's primary colour is the stock library blue", () => {
    // ← AC2
    // Only a dark scheme exists — no light one to fall back or switch to.
    expect(theme.colorSchemes?.dark).toBeTruthy();
    expect(theme.colorSchemes?.light).toBeUndefined();
    expect(Object.keys(theme.colorSchemes ?? {})).toEqual(["dark"]);

    // The scheme's own declared mode agrees.
    expect(theme.colorSchemes?.dark?.palette?.mode).toBe("dark");

    // No colour scheme on the theme still carries the create-theme-default
    // blue as its primary colour — checked against every scheme the theme
    // declares, not just the one MUI happens to pick as default, so this
    // does not pass by accident if a stray light scheme sneaks back in.
    for (const scheme of Object.values(theme.colorSchemes ?? {})) {
      const primaryMain = scheme?.palette?.primary?.main;
      expect(primaryMain).toBeTruthy();
      expect(String(primaryMain).toLowerCase()).not.toBe(STOCK_MUI_BLUE);
    }

    // The theme's own active palette (what components actually read) is the
    // same story.
    expect(theme.palette.mode).toBe("dark");
    expect(theme.palette.primary.main.toLowerCase()).not.toBe(STOCK_MUI_BLUE);
  });
});
