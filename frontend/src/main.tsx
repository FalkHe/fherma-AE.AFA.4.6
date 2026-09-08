// React root: the provider stack, nothing else (step-0.1.md §6.2). Exact
// nesting is load-bearing — theme outermost so CssBaseline covers
// everything, the router innermost so a test can substitute a MemoryRouter.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { I18nextProvider } from "react-i18next";
import { QueryClientProvider } from "@tanstack/react-query";
// react-router@8.3 exports `BrowserRouter` from the root package itself, not
// from "react-router/dom" — verified against the installed package (that
// subpath only carries the RSC/hydration-only exports in this version).
import { BrowserRouter } from "react-router";

import App from "./App";
import i18n from "./core/i18n";
import { createQueryClient } from "./core/queryClient";
import { theme } from "./core/theme";

const queryClient = createQueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider theme={theme} noSsr>
      <CssBaseline />
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </I18nextProvider>
    </ThemeProvider>
  </StrictMode>,
);
