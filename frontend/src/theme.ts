import { createTheme } from "@mui/material/styles";

/**
 * Application theme.
 *
 * `colorSchemes` (MUI v6+) is what makes `system | light | dark` a config
 * block instead of two hand-maintained themes: MUI generates one CSS variable
 * stylesheet per scheme and swaps them via `colorSchemeSelector`.
 *
 * `colorSchemeSelector: "class"` is required for *explicit* user overrides —
 * the default `"media"` selector can only follow `prefers-color-scheme` and
 * would make a light/dark toggle impossible. ThemeProvider persists an
 * explicit choice under the `mui-mode` localStorage key on its own; nothing
 * needs to be stored by the application.
 */
export const theme = createTheme({
  colorSchemes: { light: true, dark: true },
  cssVariables: { colorSchemeSelector: "class" },
  components: {
    // Every <Icon> renders a Material Symbols glyph, so the font class is set
    // once here rather than at each call site.
    MuiIcon: {
      defaultProps: { baseClassName: "material-symbols-outlined" },
    },
  },
});

/** Modes offered by the theme-mode toggle, in cycle order. */
export const themeModes = ["system", "light", "dark"] as const;

export type ThemeMode = (typeof themeModes)[number];
