// Reproduces the provider stack `main.tsx` mounts (ui-spec.md §10, step-0.1.md
// §6.2 "Provider composition"), minus `StrictMode` and with a `MemoryRouter`
// standing in for `BrowserRouter` — the substitution `App.tsx` is built to
// tolerate (it renders `<Routes>` only, no router of its own; criterion 46).
// A fresh `QueryClient` is created per render so no state leaks between
// tests.
import { type ReactElement, type ReactNode, useEffect, useRef } from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { I18nextProvider } from "react-i18next";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation, useNavigate, type NavigateFunction } from "react-router";

import { theme } from "../core/theme";
import i18n from "../core/i18n";
import { createQueryClient } from "../core/queryClient";
import App from "../App";

// `react-refresh/only-export-components` assumes every file it lints is a
// Fast Refresh boundary in the running app. This one is test-only — Vitest
// never hot-reloads it, and it is not part of the `main.tsx` module graph —
// so the rule's premise does not apply; splitting these single-caller
// composition helpers into their own files to satisfy it would be
// restructuring for a warning with nothing behind it in this context.
// eslint-disable-next-line react-refresh/only-export-components
function Providers({ children, initialEntries }: { children: ReactNode; initialEntries: string[] }) {
  return (
    <ThemeProvider theme={theme} noSsr defaultMode="dark">
      <CssBaseline />
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={createQueryClient()}>
          <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
        </QueryClientProvider>
      </I18nextProvider>
    </ThemeProvider>
  );
}

type RenderWithProvidersOptions = { route?: string } & Omit<RenderOptions, "wrapper">;

/** Renders one component (a route element, a form, …) inside the real provider stack. */
export function renderWithProviders(ui: ReactElement, options: RenderWithProvidersOptions = {}) {
  const { route = "/", ...renderOptions } = options;
  return render(ui, {
    wrapper: ({ children }) => <Providers initialEntries={[route]}>{children}</Providers>,
    ...renderOptions,
  });
}

interface RouterProbeApi {
  navigate: NavigateFunction;
  getPathname: () => string;
}

// A sibling of <App/> inside the same MemoryRouter, exposing `navigate` and
// the live location through public router hooks only — no reach into
// react-router internals — so tests can assert `replace` semantics (going
// back after a `replace` navigation must not resurrect the replaced screen).
// Same false positive as `Providers` above: test-only, not a Fast Refresh
// boundary.
// eslint-disable-next-line react-refresh/only-export-components
function RouterProbe({ onReady }: { onReady: (api: RouterProbeApi) => void }) {
  const navigate = useNavigate();
  const location = useLocation();
  const locationRef = useRef(location);

  // Sync the ref to the latest render's location. This runs as a commit
  // effect (after render), not during render itself — mutating a ref while
  // rendering is what `eslint-plugin-react-hooks`' `refs` rule (bundled in
  // its `recommended` config from v7) flags, because it can defeat React
  // Compiler's memoization assumptions. Deferring the write by one commit
  // costs nothing here: `getPathname()` is only ever read from test code via
  // `waitFor`/after a `user-event` interaction, both of which already wait
  // for effects to flush, so this is observably identical to writing the ref
  // synchronously during render.
  useEffect(() => {
    locationRef.current = location;
  });

  useEffect(() => {
    onReady({ navigate, getPathname: () => locationRef.current.pathname });
    // `navigate` and `onReady` are stable for the component's lifetime here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}

/** Renders the whole app (providers + `<App/>`) at a given starting location. */
export function renderApp(initialEntries: string[] = ["/"]) {
  let api: RouterProbeApi | undefined;

  const utils = render(
    <Providers initialEntries={initialEntries}>
      <RouterProbe
        onReady={(readyApi) => {
          api = readyApi;
        }}
      />
      <App />
    </Providers>,
  );

  return {
    ...utils,
    /** Navigates back one entry in the in-memory history stack. */
    goBack: () => api!.navigate(-1),
    /** The current route's pathname, read live off `useLocation()`. */
    getPathname: () => api!.getPathname(),
  };
}
