// WI1 (docs/intents/007-initial-frontend, sprint 03): the theme is built
// from the Goblin Pub design system's tokens (`./tokens/*.css`), not
// literals, and only the dark scheme exists. `vitest.config.ts` sets
// `css: false`, so the token stylesheets never evaluate here — every
// assertion reads the theme object's own values (`var(--…)` strings), never
// a computed/resolved colour.
import { describe, expect, it } from "vitest";

import { theme } from "./index";

describe("core/theme", () => {
  it("has exactly one colour scheme: dark", () => {
    expect(Object.keys(theme.colorSchemes)).toEqual(["dark"]);
    expect(theme.colorSchemes.dark).toBeTruthy();
    expect(theme.defaultColorScheme).toBe("dark");
    expect(theme.palette.mode).toBe("dark");
  });

  it("reads back palette colours as token references, not literals", () => {
    const { palette } = theme.colorSchemes.dark!;
    expect(palette.primary?.main).toBe("var(--accent)");
    expect(palette.primary?.light).toBe("var(--accent-hover)");
    expect(palette.primary?.dark).toBe("var(--accent-press)");
    expect(palette.primary?.contrastText).toBe("var(--text-on-accent)");
    expect(palette.secondary?.main).toBe("var(--accent-secondary)");
    expect(palette.error?.main).toBe("var(--danger)");
    expect(palette.warning?.main).toBe("var(--warning)");
    expect(palette.info?.main).toBe("var(--info)");
    expect(palette.success?.main).toBe("var(--success)");
    expect(palette.background?.default).toBe("var(--surface-app)");
    expect(palette.background?.paper).toBe("var(--surface-card)");
    expect(palette.text?.primary).toBe("var(--text-primary)");
    expect(palette.text?.secondary).toBe("var(--text-secondary)");
    expect(palette.divider).toBe("var(--border-soft)");
  });

  it("never carries the stock MUI blue on any palette colour", () => {
    const { palette } = theme.colorSchemes.dark!;
    const stockBlue = "#1976d2";
    for (const key of ["primary", "secondary", "error", "warning", "info", "success"] as const) {
      const main = palette[key]?.main;
      expect(String(main).toLowerCase()).not.toBe(stockBlue);
    }
  });

  it("exposes the organic radii as theme (shape) values pointing at their tokens", () => {
    expect(theme.shape.borderRadiusOrganic).toBe("var(--radius-organic)");
    expect(theme.shape.borderRadiusOrganicSoft).toBe("var(--radius-organic-soft)");
    expect(theme.shape.borderRadiusPill).toBe("var(--radius-pill)");
  });

  it("reads back shadows as shadow-token references, 25 elevations with 0 = none", () => {
    expect(theme.shadows).toHaveLength(25);
    expect(theme.shadows[0]).toBe("none");
    for (const elevation of theme.shadows.slice(1)) {
      expect(elevation).toMatch(/^var\(--shadow-(sm|md|lg|overlay)\)$/);
    }
  });

  it("reads back transition easings as token references", () => {
    const { easing } = theme.transitions;
    expect(easing.easeInOut).toBe("var(--ease-standard)");
    expect(easing.easeOut).toBe("var(--ease-out-soft)");
    expect(easing.easeIn).toBe("var(--ease-in)");
  });

  it("uses the real token durations, not the reduced-motion override the manifest reports", () => {
    // Trap noted in the sprint brief: `_ds_manifest.json` records
    // `--dur-fast: 0ms` because it captured the `prefers-reduced-motion`
    // override in `tokens/motion.css`, not the base duration (150ms).
    const { duration } = theme.transitions;
    expect(duration.shorter).toBe(150);
    expect(duration.standard).toBe(220);
    expect(duration.complex).toBe(400);
    expect(duration.shorter).not.toBe(0);
    expect(duration.standard).not.toBe(0);
    expect(duration.complex).not.toBe(0);
  });

  it("builds typography from the token font families, sizes and weights", () => {
    expect(theme.typography.fontFamily).toBe("var(--font-body)");
    expect(theme.typography.h1.fontFamily).toBe("var(--font-display)");
    expect(theme.typography.h1.fontSize).toBe("var(--text-display)");
    expect(theme.typography.h1.fontWeight).toBe("var(--weight-bold)");
    expect(theme.typography.body1.fontSize).toBe("var(--text-body)");
  });
});
