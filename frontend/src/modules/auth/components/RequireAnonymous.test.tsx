// UI-30, UI-39 (ui-spec.md §6.4). RequireAuth's own pending/error/redirect
// states are exercised where they matter to the user — the dashboard — in
// modules/playthrough/routes/DashboardRoute.test.tsx.
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { renderApp } from "../../../test/render";
import { deferredResponse, mockRoute } from "../../../test/network";

function stubAuthenticatedSession() {
  mockRoute("GET", "/api/v1/users/me", {
    status: 200,
    body: { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" },
    headers: { "X-CSRF-Token": "csrf-token-value" },
  });
}

describe.each(["/signin", "/signup"] as const)("RequireAnonymous guard on %s", (path) => {
  it(`UI-39: while the session read is in flight, shows the full-viewport spinner and no form — no field steals autoFocus`, async () => {
    const pending = deferredResponse();
    mockRoute("GET", "/api/v1/users/me", () => pending.promise);

    renderApp([path]);

    expect(screen.getByRole("progressbar", { name: /loading/i })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /username/i })).not.toBeInTheDocument();

    pending.resolve({
      status: 401,
      body: { error: { code: "NOT_AUTHENTICATED", message: "Authentication required.", details: null } },
    });
    await waitFor(() => expect(screen.queryByRole("progressbar")).not.toBeInTheDocument());
  });

  it("UI-30: an authenticated visitor is redirected to / with no message", async () => {
    stubAuthenticatedSession();
    // The dashboard now lives at `/` (sprint 007/07 WI1) and makes this read.
    mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });
    const app = renderApp([path]);

    await waitFor(() => expect(app.getPathname()).toBe("/"));
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Welcome back, thorin.");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
