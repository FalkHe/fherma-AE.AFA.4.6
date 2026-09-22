// Acceptance test for sprint 007/04 "guarded app shell" AC2: a signed-out
// visitor to a protected address is sent to sign-in and, after signing in,
// lands back on that exact address — not the landing page — while a visitor
// who goes to sign-in directly still ends on the landing page. Driven
// through the real guard and the real sign-in form (SignInRoute.test.tsx's
// own pattern), never by inspecting how the address was remembered.
import { describe, expect, it } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderApp } from "./test/render";
import { mockRoute } from "./test/network";

function stubUnauthenticated() {
  mockRoute("GET", "/api/v1/users/me", {
    status: 401,
    body: { error: { code: "NOT_AUTHENTICATED", message: "x", details: null } },
  });
}

function stubSignInSuccess(username = "thorin") {
  mockRoute("POST", "/api/v1/auth/sign-in", {
    status: 200,
    body: { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username, createdAt: "2026-09-08T12:34:56.789012+00:00" },
    headers: { "X-CSRF-Token": "csrf-token-value" },
  });
}

async function signIn() {
  const username = await screen.findByRole("textbox", { name: /username/i });
  const password = screen.getByLabelText(/password/i);
  const user = userEvent.setup();
  await user.type(username, "thorin");
  await user.type(password, "hunter-of-orcs");
  await user.click(screen.getByRole("button", { name: /sign in/i }));
}

describe("returning to the requested address (AC2)", () => {
  it("AC2: a deep link to /dashboard bounces to sign-in and back to /dashboard; a direct sign-in still ends on /", async () => {
    // ← AC2
    stubUnauthenticated();
    stubSignInSuccess();
    const dashboardApp = renderApp(["/dashboard"]);

    await waitFor(() => expect(dashboardApp.getPathname()).toBe("/signin"));
    await screen.findByRole("heading", { level: 1, name: "Sign in" });

    await signIn();

    await waitFor(() => expect(dashboardApp.getPathname()).toBe("/dashboard"));
    // Not the landing page: its greeting heading must not be showing.
    expect(screen.queryByText(/welcome, thorin\./i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "Sign in" })).not.toBeInTheDocument();
    cleanup();

    stubUnauthenticated();
    stubSignInSuccess();
    const directApp = renderApp(["/signin"]);

    await screen.findByRole("heading", { level: 1, name: "Sign in" });
    await signIn();

    await waitFor(() => expect(directApp.getPathname()).toBe("/"));
    expect(await screen.findByText(/welcome, thorin\./i)).toBeInTheDocument();
  });
});
