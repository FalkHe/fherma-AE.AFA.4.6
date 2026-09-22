// Acceptance test for sprint 007/04 "guarded app shell" AC3: the shared
// header shows the wordmark "The Goblin's Tavern" and an account button
// whose menu carries the player's name and a sign out; signing out returns
// to sign-in. Driven through the real guarded shell on a signed-in page
// (HomeRoute.test.tsx's own stubbing pattern), never by inspecting the
// account menu component directly.
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderApp } from "./test/render";
import { mockRoute } from "./test/network";

const USER = { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };
const APP_TITLE = "The Goblin's Tavern";

function stubAuthenticated() {
  mockRoute("GET", "/api/v1/users/me", { status: 200, body: USER, headers: { "X-CSRF-Token": "csrf-token-value" } });
  // The dashboard now lives at `/` (sprint 007/07 WI1) and makes this read.
  mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });
}

describe("header and account menu (AC3)", () => {
  it("AC3: the header shows the wordmark (not a heading) and an account button whose menu carries the player's name and sign out; signing out returns to sign-in", async () => {
    // ← AC3
    stubAuthenticated();
    mockRoute("POST", "/api/v1/auth/sign-out", { status: 204 });
    const app = renderApp(["/"]);

    await screen.findByRole("heading", { level: 1 });

    // Wordmark is shown, and is not itself a heading element.
    const wordmark = screen.getByText(APP_TITLE);
    expect(wordmark).toBeInTheDocument();
    const headings = screen.getAllByRole("heading");
    expect(headings.some((heading) => heading.textContent === APP_TITLE)).toBe(false);

    // Account trigger: named "Account", opens a menu, shows the initial.
    const trigger = screen.getByRole("button", { name: "Account" });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveTextContent("T");

    const user = userEvent.setup();
    await user.click(trigger);

    const menu = await screen.findByRole("menu");
    expect(menu).toHaveTextContent("thorin");
    const signOutItem = screen.getByRole("menuitem", { name: /sign out/i });

    await user.click(signOutItem);

    await waitFor(() => expect(app.getPathname()).toBe("/signin"));
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
  });
});
