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

const RUN_ID = "01J000000000000000000RUN1";

const RUN_OVERVIEW = {
  id: RUN_ID,
  campaignId: "greenhollow",
  contentVersion: "v1",
  title: null,
  status: "setup",
  createdAt: "2026-09-08T12:34:56.789012+00:00",
  campaignTitle: "The Rotting Stump",
  campaignSummary: "A pub that hides in the wood and only opens for people it likes.",
  unavailable: false,
  members: [],
  adventures: [],
};

describe("returning to the requested address (AC2)", () => {
  it(`AC2: a deep link to /runs/${RUN_ID} bounces to sign-in and back there; a direct sign-in still ends on /`, async () => {
    // ← AC2
    stubUnauthenticated();
    stubSignInSuccess();
    mockRoute("GET", `/api/v1/playthrough/runs/${RUN_ID}/overview`, { status: 200, body: RUN_OVERVIEW });
    const runApp = renderApp([`/runs/${RUN_ID}`]);

    await waitFor(() => expect(runApp.getPathname()).toBe("/signin"));
    await screen.findByRole("heading", { level: 1, name: "Sign in" });

    await signIn();

    await waitFor(() => expect(runApp.getPathname()).toBe(`/runs/${RUN_ID}`));
    // Not the landing page: its greeting heading must not be showing.
    expect(screen.queryByText(/welcome back, thorin\./i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "Sign in" })).not.toBeInTheDocument();
    cleanup();

    stubUnauthenticated();
    stubSignInSuccess();
    // The dashboard now lives at `/` (sprint 007/07 WI1) and makes this read.
    mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });
    const directApp = renderApp(["/signin"]);

    await screen.findByRole("heading", { level: 1, name: "Sign in" });
    await signIn();

    await waitFor(() => expect(directApp.getPathname()).toBe("/"));
    expect(await screen.findByText(/welcome back, thorin\./i)).toBeInTheDocument();
  });
});
