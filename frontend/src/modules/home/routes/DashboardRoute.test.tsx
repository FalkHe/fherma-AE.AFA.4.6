// The second protected address (AC2's precondition): an otherwise empty
// page proving the guard declared once in App.tsx (AC1) covers more than
// the landing route — same redirect-when-signed-out, same no-header-while-
// pending behaviour, without either being repeated here.
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { renderApp } from "../../../test/render";
import { deferredResponse, mockRoute } from "../../../test/network";

const USER = { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };

function stubAuthenticated() {
  mockRoute("GET", "/api/v1/users/me", { status: 200, body: USER, headers: { "X-CSRF-Token": "csrf-token-value" } });
}

function stubUnauthenticated() {
  mockRoute("GET", "/api/v1/users/me", {
    status: 401,
    body: { error: { code: "NOT_AUTHENTICATED", message: "x", details: null } },
  });
}

describe("DashboardRoute and the shared guard on /dashboard", () => {
  it("renders its heading and sets a distinct document title when signed in", async () => {
    stubAuthenticated();
    renderApp(["/dashboard"]);

    const heading = await screen.findByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("Dashboard");
    await waitFor(() => expect(document.title).toContain("Dashboard"));
    expect(document.title).toContain("The Goblin's Tavern");
  });

  it("redirects a signed-out visitor to /signin", async () => {
    stubUnauthenticated();
    const app = renderApp(["/dashboard"]);

    await waitFor(() => expect(app.getPathname()).toBe("/signin"));
    await screen.findByRole("heading", { level: 1, name: "Sign in" });
  });

  it("shows no header while the session read is pending, proving the guard sits outside the shell here too", async () => {
    const pending = deferredResponse();
    mockRoute("GET", "/api/v1/users/me", () => pending.promise);

    renderApp(["/dashboard"]);

    expect(screen.getByRole("progressbar", { name: /loading/i })).toBeInTheDocument();
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();

    pending.resolve({ status: 200, body: USER, headers: { "X-CSRF-Token": "csrf-token-value" } });
    await screen.findByRole("banner");
  });
});
