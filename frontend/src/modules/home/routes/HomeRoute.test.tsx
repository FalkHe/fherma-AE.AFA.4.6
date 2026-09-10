// UI-21 … UI-29, UI-42 (ui-spec.md §12, §3.3, §6.3), plus step-0.1.md
// criterion 45 (the session-expired warning's exact trigger set). Criterion
// 37/38 (CSRF re-acquisition and header presence) live in
// modules/auth/csrf.test.tsx, next to the other request-shape assertions.
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderApp } from "../../../test/render";
import { deferredResponse, mockRoute } from "../../../test/network";

const USER = { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };

const copy = {
  appTitle: "AI Dungeon Master",
  greeting: "Welcome, thorin.",
  sessionExpired: "Your session ended. Please sign in again.",
  signOutError: "Could not sign you out. Please try again.",
  retry: "Try again",
  networkError: "Cannot reach the server. Check your connection and try again.",
};

function stubAuthenticated() {
  mockRoute("GET", "/api/v1/users/me", {
    status: 200,
    body: USER,
    headers: { "X-CSRF-Token": "csrf-token-value" },
  });
}

describe("HomeRoute and the RequireAuth guard on / (UI-21 … UI-29, UI-42)", () => {
  it("UI-21 / UI-22: while the session read is in flight shows a labelled spinner and no AppBar; resolves to /signin with no message for an unauthenticated visitor", async () => {
    const pending = deferredResponse();
    mockRoute("GET", "/api/v1/users/me", () => pending.promise);

    const app = renderApp(["/"]);

    expect(screen.getByRole("progressbar", { name: /loading/i })).toBeInTheDocument();
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();

    pending.resolve({
      status: 401,
      body: { error: { code: "NOT_AUTHENTICATED", message: "Authentication required.", details: null } },
    });

    await waitFor(() => expect(app.getPathname()).toBe("/signin"));
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
    expect(screen.queryByText(copy.sessionExpired)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("UI-23 / UI-24 / UI-42: an authenticated / renders the AppBar (non-heading title), a Sign out button, and only the greeting h1", async () => {
    stubAuthenticated();
    renderApp(["/"]);

    const heading = await screen.findByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent(copy.greeting);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();

    const title = screen.getByText(copy.appTitle);
    expect(title.tagName).toBe("P"); // branding, not the document heading (§3.3)
  });

  it("UI-25: the first tab stop on / is the Sign out button", async () => {
    stubAuthenticated();
    renderApp(["/"]);
    const heading = await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(heading).toHaveFocus());

    // `document.body` carries no `tabindex`, so it is not a focusable target:
    // `body.focus()` is a no-op and leaves the heading focused, silently
    // defeating the "first tab stop" premise below. `blur()` on the
    // currently-focused element is what actually returns
    // `document.activeElement` to `body`, matching a real page load where
    // nothing has focus yet.
    heading.blur();
    const user = userEvent.setup();
    await user.tab();

    expect(screen.getByRole("button", { name: /sign out/i })).toHaveFocus();
  });

  it("UI-26: signing out disables the button and shows loading, then redirects via replace so Back does not restore the authenticated home page", async () => {
    stubAuthenticated();
    const pending = deferredResponse();
    mockRoute("POST", "/api/v1/auth/sign-out", () => pending.promise);
    const app = renderApp(["/"]);
    await screen.findByRole("heading", { level: 1 });

    const user = userEvent.setup();
    const signOutButton = screen.getByRole("button", { name: /sign out/i });
    await user.click(signOutButton);

    await waitFor(() => expect(signOutButton).toBeDisabled());

    pending.resolve({ status: 204 });

    await waitFor(() => expect(app.getPathname()).toBe("/signin"));

    app.goBack();
    await waitFor(() => expect(app.getPathname()).toBe("/signin"));
    expect(screen.queryByText(copy.greeting)).not.toBeInTheDocument();
  });

  it.each([
    { label: "403", status: 403, code: "CSRF_TOKEN_INVALID" },
    { label: "500", status: 500, code: "INTERNAL_ERROR" },
  ])("UI-27: a failed sign-out ($label) leaves the user signed in and shows the sign-out error alert above the greeting", async ({ status, code }) => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/auth/sign-out", {
      status,
      body: { error: { code, message: "x", details: null } },
    });
    const app = renderApp(["/"]);
    const heading = await screen.findByRole("heading", { level: 1 });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /sign out/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(copy.signOutError);
    expect(app.getPathname()).toBe("/");
    expect(heading).toHaveTextContent(copy.greeting);
    expect(screen.getByRole("button", { name: /sign out/i })).not.toBeDisabled();
    // "above the greeting" — the alert must precede the h1 in DOM order.
    expect(alert.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("UI-27: a 401 on sign-out is the deliberate case — success handler, redirect, no alert", async () => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/auth/sign-out", {
      status: 401,
      body: { error: { code: "SESSION_EXPIRED", message: "x", details: null } },
    });
    const app = renderApp(["/"]);
    await screen.findByRole("heading", { level: 1 });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => expect(app.getPathname()).toBe("/signin"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(copy.sessionExpired)).not.toBeInTheDocument();
  });

  it("UI-28 / criterion 45: a cold load answering 401 SESSION_EXPIRED redirects to /signin and shows the warning", async () => {
    mockRoute("GET", "/api/v1/users/me", {
      status: 401,
      body: { error: { code: "SESSION_EXPIRED", message: "x", details: null } },
    });
    const app = renderApp(["/"]);

    await waitFor(() => expect(app.getPathname()).toBe("/signin"));
    expect(await screen.findByText(copy.sessionExpired)).toBeInTheDocument();
  });

  it("UI-28 / criterion 45: a cold load answering 401 NOT_AUTHENTICATED redirects with no warning", async () => {
    mockRoute("GET", "/api/v1/users/me", {
      status: 401,
      body: { error: { code: "NOT_AUTHENTICATED", message: "x", details: null } },
    });
    const app = renderApp(["/"]);

    await waitFor(() => expect(app.getPathname()).toBe("/signin"));
    expect(screen.queryByText(copy.sessionExpired)).not.toBeInTheDocument();
  });

  it("criterion 45: a direct visit to /signin never shows the warning, whatever the code", async () => {
    mockRoute("GET", "/api/v1/users/me", {
      status: 401,
      body: { error: { code: "SESSION_EXPIRED", message: "x", details: null } },
    });
    renderApp(["/signin"]);

    await screen.findByRole("heading", { level: 1, name: "Sign in" });
    expect(screen.queryByText(copy.sessionExpired)).not.toBeInTheDocument();
  });

  it("UI-29: a session read failing with a network error shows a retry alert and does not redirect", async () => {
    mockRoute("GET", "/api/v1/users/me", () => {
      throw new Error("simulated network failure");
    });
    const app = renderApp(["/"]);

    expect(await screen.findByText(copy.networkError)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: copy.retry })).toBeInTheDocument();
    expect(app.getPathname()).toBe("/");
  });

  it("UI-29: the retry control refetches the session and can recover", async () => {
    let attempts = 0;
    mockRoute("GET", "/api/v1/users/me", () => {
      attempts += 1;
      if (attempts === 1) {
        throw new Error("simulated network failure");
      }
      return { status: 200, body: USER, headers: { "X-CSRF-Token": "csrf-token-value" } };
    });
    renderApp(["/"]);

    const retryButton = await screen.findByRole("button", { name: copy.retry });
    const user = userEvent.setup();
    await user.click(retryButton);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(copy.greeting);
  });
});
