// Criterion 46's behavioural half (App.tsx contains no provider/router is a
// static grep — see structure.test.ts) and UI-38 (per-route document titles).
// The catch-all route (§6.2 routing table) is exercised here too.
import { describe, expect, it } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";

import { renderApp } from "./test/render";
import { mockRoute } from "./test/network";

const USER = { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };

function stubUnauthenticated() {
  mockRoute("GET", "/api/v1/users/me", {
    status: 401,
    body: { error: { code: "NOT_AUTHENTICATED", message: "x", details: null } },
  });
}

function stubAuthenticated() {
  mockRoute("GET", "/api/v1/users/me", { status: 200, body: USER, headers: { "X-CSRF-Token": "t" } });
  // The dashboard now lives at `/` (sprint 007/07 WI1) — every authenticated
  // render of it makes this read.
  mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });
}

describe("App routing (criterion 46, UI-38)", () => {
  it("criterion 46: renders inside qa-frontend's own provider wrapper without throwing", async () => {
    stubUnauthenticated();
    renderApp(["/signin"]);
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Sign in");
  });

  it("UI-38: /signin, /signup and / each set a distinct document title, none of them the framework default", async () => {
    // Each `renderApp()` mounts a fresh tree without unmounting the previous
    // one (RTL's `render` appends to `document.body`), so three renders in
    // one test would otherwise leave three headings in the document at once
    // and every `screen.findByRole("heading", …)` below would be ambiguous.
    // `cleanup()` between renders keeps each stage isolated.
    stubUnauthenticated();
    renderApp(["/signin"]);
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(document.title).toContain("Sign in"));
    expect(document.title).not.toBe("Vite + React");
    cleanup();

    stubUnauthenticated();
    renderApp(["/signup"]);
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(document.title).toContain("Create an account"));
    expect(document.title).not.toBe("Vite + React");
    cleanup();

    stubAuthenticated();
    renderApp(["/"]);
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(document.title).toContain("The Goblin's Tavern"));
    expect(document.title).not.toBe("Vite + React");
  });

  it("an unknown path redirects to / (and onward to /signin when signed out)", async () => {
    stubUnauthenticated();
    const app = renderApp(["/does-not-exist"]);
    await waitFor(() => expect(app.getPathname()).toBe("/signin"));
  });

  it("an unknown path redirects to / and lands there when signed in", async () => {
    stubAuthenticated();
    const app = renderApp(["/does-not-exist"]);
    await waitFor(() => expect(app.getPathname()).toBe("/"));
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Welcome back, thorin.");
  });
});
