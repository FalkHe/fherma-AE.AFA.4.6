// Sprint 007/05 WI1, AC1/AC5. Rendered through the real guard (`RequireAuth`
// behind every signed-in route) via `renderApp`, so the session read it
// makes is always stubbed first. `PartySection` (WI2) is imported but not
// yet built this sprint — a test run before it lands fails only on that
// unresolved import, nothing here.
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderApp } from "../../../test/render";
import { mockRoute } from "../../../test/network";

const USER = { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };

const OVERVIEW = {
  id: "01J000000000000000000RUN1",
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

function stubAuthenticated() {
  mockRoute("GET", "/api/v1/users/me", { status: 200, body: USER, headers: { "X-CSRF-Token": "csrf-token-value" } });
}

describe("RunRoute on /runs/:runId (AC1, AC5)", () => {
  it("renders the campaign title, description and status badge from one overview read", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs/abc/overview", { status: 200, body: OVERVIEW });

    renderApp(["/runs/abc"]);

    const heading = await screen.findByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("The Rotting Stump");
    expect(screen.getByText(OVERVIEW.campaignSummary)).toBeInTheDocument();
    expect(screen.getByText("New")).toBeInTheDocument();
  });

  it("offers a retry that recovers from a failed overview read", async () => {
    stubAuthenticated();
    let attempts = 0;
    mockRoute("GET", "/api/v1/playthrough/runs/abc/overview", () => {
      attempts += 1;
      if (attempts === 1) {
        throw new Error("simulated network failure");
      }
      return { status: 200, body: OVERVIEW };
    });

    renderApp(["/runs/abc"]);

    const retryButton = await screen.findByRole("button", { name: "Try again" });
    expect(screen.getByText("Cannot reach the server. Check your connection and try again.")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(retryButton);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("The Rotting Stump");
  });

  it("shows a plain not-found message for a run that does not exist", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs/missing/overview", {
      status: 404,
      body: { error: { code: "NOT_FOUND", message: "x", details: null } },
    });

    renderApp(["/runs/missing"]);

    expect(await screen.findByText("This run could not be found.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
  });

  it("the back link returns to the campaigns page", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs/abc/overview", { status: 200, body: OVERVIEW });

    const app = renderApp(["/runs/abc"]);

    const backLink = await screen.findByRole("link", { name: /campaigns/i });
    expect(backLink).toHaveAttribute("href", "/");

    const user = userEvent.setup();
    await user.click(backLink);
    await waitFor(() => expect(app.getPathname()).toBe("/"));
  });
});
