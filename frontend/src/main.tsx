import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import { BrowserRouter } from "react-router";

// Provides the Material Symbols font used by every <Icon>.
import "material-symbols/outlined.css";

import App from "./App";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { i18n } from "./i18n";
import { queryClient } from "./queryClient";
import { theme } from "./theme";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Root element #root is missing from index.html");
}

createRoot(rootElement).render(
  <StrictMode>
    {/* defaultMode "system" applies until the user picks a mode explicitly;
        ThemeProvider then persists that override in localStorage. */}
    <ThemeProvider theme={theme} defaultMode="system">
      <CssBaseline enableColorScheme />
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <AppErrorBoundary>
              <App />
            </AppErrorBoundary>
          </BrowserRouter>
        </QueryClientProvider>
      </I18nextProvider>
    </ThemeProvider>
  </StrictMode>,
);
