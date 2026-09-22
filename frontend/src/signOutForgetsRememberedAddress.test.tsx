// Regression for sprint 007/04 AC2: a remembered protected address must not
// outlive the sign-in it was meant for. Signing out of a page RequireAuth
// once bounced the visitor to reach can itself re-stamp that page onto
// /signin's remembered address (RequireAuth briefly still sees the old page
// with the now-cleared user and redirects there itself) — and unless that
// stamp is cleared, a *later, unrelated* sign-in in the same tab wrongly
// replays it. Exercised through one continuous render (no remount between
// steps, real guards, real sign-in/sign-out forms) so the carry-over between
// them can actually be observed, the way `returnToRequestedPage.test.tsx`
// exercises the deep-link half of the same criterion.
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
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

function stubSignOutSuccess() {
  mockRoute("POST", "/api/v1/auth/sign-out", { status: 204 });
}

async function signIn() {
  const username = await screen.findByRole("textbox", { name: /username/i });
  const password = screen.getByLabelText(/password/i);
  const user = userEvent.setup();
  await user.type(username, "thorin");
  await user.type(password, "hunter-of-orcs");
  await user.click(screen.getByRole("button", { name: /sign in/i }));
}

async function signOut() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Account" }));
  await user.click(await screen.findByRole("menuitem", { name: /sign out/i }));
}

describe("signing out forgets a remembered address (AC2)", () => {
  it("bounce → sign in → sign out → sign in again lands on / — not the address signed out of", async () => {
    // ← AC2
    stubUnauthenticated();
    stubSignInSuccess();
    stubSignOutSuccess();
    const app = renderApp(["/dashboard?tab=quests"]);

    // Genuine bounce: reaches the sign-in it was meant for.
    await waitFor(() => expect(app.getPathname()).toBe("/signin"));
    await signIn();
    await waitFor(() => expect(app.getPathname()).toBe("/dashboard"));

    // Sign out of that same remembered page, then sign in again, unprompted
    // this time — the address just signed out of must not resurface.
    await signOut();
    await waitFor(() => expect(app.getPathname()).toBe("/signin"));
    await signIn();

    await waitFor(() => expect(app.getPathname()).toBe("/"));
    expect(await screen.findByText(/welcome, thorin\./i)).toBeInTheDocument();
  });
});
