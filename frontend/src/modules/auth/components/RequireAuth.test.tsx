// Recovered from `modules/home`'s retired `HomeRoute.test.tsx`
// (git show main:frontend/src/modules/home/routes/HomeRoute.test.tsx) —
// deleted along with the rest of that module when the landing screen moved
// to `playthrough/routes/DashboardRoute` (sprint 007/07 WI1). These cases
// assert `RequireAuth` itself — the session-expired warning's exact trigger
// set (step-0.1.md criterion 45) and the unreachable-server retry path
// (UI-29) — not any particular screen, so they belong here rather than with
// one route's own test. UI-21/22/23/24/42 (the guard's pending/redirect/
// authenticated-render shell) moved instead onto
// `playthrough/routes/DashboardRoute.test.tsx`, the address they're now
// exercised through.
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderApp } from "../../../test/render";
import { mockRoute } from "../../../test/network";

const USER = { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };

const copy = {
  // "Welcome, thorin." in the original — updated for the dashboard's own
  // greeting copy (sprint 007/07 WI1, AC5); every other assertion here is
  // unchanged from the original.
  greeting: "Welcome back, thorin.",
  sessionExpired: "Your session ended. Please sign in again.",
  retry: "Try again",
  networkError: "Cannot reach the server. Check your connection and try again.",
};

// The dashboard now lives at `/` (sprint 007/07 WI1) and reads this once
// `RequireAuth` actually renders it — only the recovery case below ever
// reaches that far; the others redirect or error out of `RequireAuth`
// itself before the dashboard would mount.
function stubEmptyRuns() {
  mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });
}

describe("RequireAuth guard (UI-28, UI-29, criterion 45)", () => {
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
    stubEmptyRuns();
    renderApp(["/"]);

    const retryButton = await screen.findByRole("button", { name: copy.retry });
    const user = userEvent.setup();
    await user.click(retryButton);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(copy.greeting);
  });
});
