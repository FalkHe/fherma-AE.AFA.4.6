// Exports the theme and nothing else — no JSX, no provider (step-0.1.md
// §6.2, UI-43). `main.tsx` is the only place that renders `ThemeProvider`.
import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  cssVariables: true,
  colorSchemes: { light: true, dark: true },
});
