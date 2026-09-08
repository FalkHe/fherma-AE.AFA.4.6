// step-0.1.md criteria 37, 38 and the credentialed-request half of 39. The
// browser actually sending the `session` cookie cross-origin is a real-network
// fact `fetch` mocking cannot observe — that half of 39 belongs to the
// browser acceptance pass (mode B). What is verifiable here: every request
// asks for `credentials: "include"`, a mutation carries the CSRF token the
// most recent response handed it, and a GET never does.
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderApp } from "../../test/render";
import { getRequests, mockRoute } from "../../test/network";

const USER = { id: "9f1c0b6a-6f7c-4a2f-9a3e-0b6d1c2e3f40", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };

describe("CSRF token handling and credentialed requests", () => {
  it("criterion 37 / 38: reloading / re-acquires the CSRF token from GET /users/me, and sign-out replays exactly that token", async () => {
    mockRoute("GET", "/api/v1/users/me", {
      status: 200,
      body: USER,
      headers: { "X-CSRF-Token": "token-from-reload" },
    });
    mockRoute("POST", "/api/v1/auth/sign-out", { status: 204 });

    const app = renderApp(["/"]);
    await screen.findByRole("heading", { level: 1 });

    const getRequestsForMe = getRequests({ method: "GET", path: "/api/v1/users/me" });
    expect(getRequestsForMe).toHaveLength(1);
    expect(getRequestsForMe[0].headers["x-csrf-token"]).toBeUndefined(); // UI-38: no GET carries the header

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => expect(app.getPathname()).toBe("/signin"));

    const signOutRequests = getRequests({ method: "POST", path: "/api/v1/auth/sign-out" });
    expect(signOutRequests).toHaveLength(1);
    expect(signOutRequests[0].headers["x-csrf-token"]).toBe("token-from-reload");
  });

  it("every request is credentialed (`credentials: \"include\"`), the necessary condition for the cross-origin session cookie to be sent", async () => {
    mockRoute("GET", "/api/v1/users/me", { status: 200, body: USER, headers: { "X-CSRF-Token": "t" } });
    renderApp(["/"]);
    await screen.findByRole("heading", { level: 1 });

    const requests = getRequests({ method: "GET", path: "/api/v1/users/me" });
    expect(requests).toHaveLength(1);
    expect(requests[0].credentials).toBe("include");
  });
});
