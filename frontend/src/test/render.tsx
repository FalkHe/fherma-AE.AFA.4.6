import { ThemeProvider } from "@mui/material/styles";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";

import { i18n } from "../i18n";
import { theme } from "../theme";

/**
 * Renders a component inside the same providers `main.tsx` mounts, so tests
 * exercise real translations, the real theme and a real query cache.
 */
export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper"> & {
    /**
     * Where the router starts. URL-driven screens (the catalogue's filters live
     * in search params) need a rendering that begins at a given URL, which is
     * also the only way to test "reload reproduces the view" as a real mount.
     */
    initialEntries?: string[];
  },
): RenderResult {
  const { initialEntries, ...renderOptions } = options ?? {};

  // A cache per render: state from one test must never decide the outcome of
  // the next one.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { refetchOnWindowFocus: false } },
  });

  function Providers({ children }: { children: ReactNode }) {
    return (
      <ThemeProvider theme={theme} defaultMode="system">
        <I18nextProvider i18n={i18n}>
          <QueryClientProvider client={queryClient}>
            <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
          </QueryClientProvider>
        </I18nextProvider>
      </ThemeProvider>
    );
  }

  return render(ui, { wrapper: Providers, ...renderOptions });
}
