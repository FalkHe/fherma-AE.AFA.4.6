// Acceptance test for sprint 007/03 "Goblin Pub theme" AC4: the product
// renamed itself to "The Goblin's Tavern" (plain ASCII apostrophe) on every
// screen and in the browser tab title. Renders each of the three existing
// screens through the real app (App.test.tsx's own pattern for exercising
// more than one route in a file: `cleanup()` between stages so each render
// is judged in isolation) rather than guessing at a wordmark component.
import { describe, expect, it } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";

import { renderApp } from "./test/render";
import { mockRoute } from "./test/network";

const APP_TITLE = "The Goblin's Tavern"; // ASCII apostrophe (U+0027), not U+2019.

const USER = { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };

function stubUnauthenticated() {
  mockRoute("GET", "/api/v1/users/me", {
    status: 401,
    body: { error: { code: "NOT_AUTHENTICATED", message: "x", details: null } },
  });
}

function stubAuthenticated() {
  mockRoute("GET", "/api/v1/users/me", { status: 200, body: USER, headers: { "X-CSRF-Token": "t" } });
  // The dashboard now lives at `/` (sprint 007/07 WI1) and makes this read.
  mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });
}

describe("product name (AC4)", () => {
  it("AC4: sign-in, sign-up and the landing page all show 'The Goblin's Tavern', and so does the tab title", async () => {
    // ← AC4
    stubUnauthenticated();
    renderApp(["/signin"]);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByText(APP_TITLE)).toBeInTheDocument();
    await waitFor(() => expect(document.title).toContain(APP_TITLE));
    cleanup();

    stubUnauthenticated();
    renderApp(["/signup"]);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByText(APP_TITLE)).toBeInTheDocument();
    await waitFor(() => expect(document.title).toContain(APP_TITLE));
    cleanup();

    stubAuthenticated();
    renderApp(["/"]);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByText(APP_TITLE)).toBeInTheDocument();
    await waitFor(() => expect(document.title).toContain(APP_TITLE));
  });
});
