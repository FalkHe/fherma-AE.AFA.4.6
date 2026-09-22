// AC3 (ui-spec.md): the header's account control. Behaviours under test —
// the "Account" trigger and its initial, the menu's username/divider/Sign
// out contents, a successful sign-out landing on /signin with no way back,
// a refused sign-out staying put and saying so inside the still-open menu,
// and a 401 (expired session) signing out silently. These cases replace
// modules/home/routes/HomeRoute.test.tsx's former UI-26/UI-27 sign-out
// cases, migrated here now that AccountMenu owns the sign-out UI itself.
//
// AccountMenu is not yet wired into App's route tree (a later work item does
// that), and `test/render.tsx`'s helpers import `App` itself — currently
// mid-flight in a parallel work item (core/layout/AppShell), which leaves
// `App`'s module graph transiently unresolvable. So this file builds the
// same provider stack `test/render.tsx`'s `Providers`/`RouterProbe` do,
// inline, rather than importing that module: same pattern, no dependency on
// `App` compiling.
import { useEffect, useRef, type ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { I18nextProvider } from "react-i18next";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation, useNavigate, type NavigateFunction } from "react-router";

import { theme } from "../../../core/theme";
import i18n from "../../../core/i18n";
import { createQueryClient } from "../../../core/queryClient";
import { mockRoute } from "../../../test/network";
import { AccountMenu } from "./AccountMenu";

const USER = { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };

const copy = {
  signOutAction: "Sign out",
  signOutError: "Could not sign you out. Please try again.",
};

function stubAuthenticated() {
  mockRoute("GET", "/api/v1/users/me", {
    status: 200,
    body: USER,
    headers: { "X-CSRF-Token": "csrf-token-value" },
  });
}

interface RouterProbeApi {
  navigate: NavigateFunction;
  getPathname: () => string;
}

function RouterProbe({ onReady }: { onReady: (api: RouterProbeApi) => void }) {
  const navigate = useNavigate();
  const location = useLocation();
  const locationRef = useRef(location);

  useEffect(() => {
    locationRef.current = location;
  });

  useEffect(() => {
    onReady({ navigate, getPathname: () => locationRef.current.pathname });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}

function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider theme={theme} noSsr defaultMode="dark">
      <CssBaseline />
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={createQueryClient()}>
          <MemoryRouter initialEntries={["/"]}>{children}</MemoryRouter>
        </QueryClientProvider>
      </I18nextProvider>
    </ThemeProvider>
  );
}

function renderMenu() {
  let api: RouterProbeApi | undefined;

  render(
    <Providers>
      <RouterProbe
        onReady={(readyApi) => {
          api = readyApi;
        }}
      />
      <AccountMenu />
    </Providers>,
  );

  return {
    goBack: () => api!.navigate(-1),
    getPathname: () => api!.getPathname(),
  };
}

async function openMenu() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Account" }));
  return user;
}

describe("AccountMenu (AC3)", () => {
  it("shows a trigger named Account whose content is the user's initial, uppercased", async () => {
    stubAuthenticated();
    renderMenu();

    const trigger = await screen.findByRole("button", { name: "Account" });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    await waitFor(() => expect(trigger).toHaveTextContent("T"));
  });

  it("shows no initial while the user is unknown", async () => {
    mockRoute("GET", "/api/v1/users/me", () => new Promise(() => {})); // never resolves
    renderMenu();

    const trigger = await screen.findByRole("button", { name: "Account" });
    expect(trigger).toHaveTextContent("");
  });

  it("opening the trigger shows a menu with the username, a divider and Sign out", async () => {
    stubAuthenticated();
    renderMenu();

    await openMenu();

    const menu = screen.getByRole("menu");
    expect(menu).toHaveTextContent("thorin");
    expect(screen.getByRole("separator")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: copy.signOutAction })).toBeInTheDocument();
  });

  it("signing out lands on /signin and Back does not restore the page", async () => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/auth/sign-out", { status: 204 });
    const app = renderMenu();
    const user = await openMenu();

    await user.click(screen.getByRole("menuitem", { name: copy.signOutAction }));

    await waitFor(() => expect(app.getPathname()).toBe("/signin"));

    app.goBack();
    await waitFor(() => expect(app.getPathname()).toBe("/signin"));
  });

  it.each([
    { label: "403", status: 403, code: "CSRF_TOKEN_INVALID" },
    { label: "500", status: 500, code: "INTERNAL_ERROR" },
  ])("a refused sign-out ($label) keeps the visitor signed in and shows the error inside the open menu", async ({ status, code }) => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/auth/sign-out", {
      status,
      body: { error: { code, message: "x", details: null } },
    });
    const app = renderMenu();
    const user = await openMenu();

    await user.click(screen.getByRole("menuitem", { name: copy.signOutAction }));

    const menu = screen.getByRole("menu");
    const alert = await screen.findByRole("alert");
    expect(menu).toContainElement(alert);
    expect(alert).toHaveTextContent(copy.signOutError);
    expect(app.getPathname()).toBe("/");
    expect(screen.getByRole("menuitem", { name: copy.signOutAction })).toBeInTheDocument();
  });

  it("an expired session (401) signs out silently — no alert, straight to /signin", async () => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/auth/sign-out", {
      status: 401,
      body: { error: { code: "SESSION_EXPIRED", message: "x", details: null } },
    });
    const app = renderMenu();
    const user = await openMenu();

    await user.click(screen.getByRole("menuitem", { name: copy.signOutAction }));

    await waitFor(() => expect(app.getPathname()).toBe("/signin"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
