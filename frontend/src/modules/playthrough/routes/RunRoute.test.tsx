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

const READY_MEMBER = { userId: "u1", username: "thorin", role: "owner", ready: true, characterName: "Doon" };
const UNREADY_MEMBER = { userId: "u1", username: "thorin", role: "owner", ready: false, characterName: null };

function adventure(id: string, title: string, status: "done" | "active" | "unplayed") {
  return { id, title, introExcerpt: `${title} teaser`, status };
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

describe("RunRoute's adventures section (sprint 007/06 WI1, AC1-AC5)", () => {
  it("AC1: renders adventures in campaign order with numeral, title and teaser", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs/abc/overview", {
      status: 200,
      body: {
        ...OVERVIEW,
        members: [READY_MEMBER],
        adventures: [
          adventure("a1", "A door in the wrong wood", "active"),
          adventure("a2", "The barrel argument", "unplayed"),
        ],
      },
    });

    renderApp(["/runs/abc"]);

    await screen.findByText("A door in the wrong wood");
    const rows = screen.getAllByText(/^(A door in the wrong wood|The barrel argument)$/);
    expect(rows.map((row) => row.textContent)).toEqual(["A door in the wrong wood", "The barrel argument"]);
    expect(screen.getByText("I")).toBeInTheDocument();
    expect(screen.getByText("II")).toBeInTheDocument();
    expect(screen.getByText("A door in the wrong wood teaser")).toBeInTheDocument();
    expect(screen.getByText("The barrel argument teaser")).toBeInTheDocument();
  });

  it("AC2: the first unplayed adventure reads Next up when the party is ready, Waiting on party otherwise", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs/ready/overview", {
      status: 200,
      body: { ...OVERVIEW, members: [READY_MEMBER], adventures: [adventure("a1", "A door in the wrong wood", "active")] },
    });
    mockRoute("GET", "/api/v1/playthrough/runs/waiting/overview", {
      status: 200,
      body: { ...OVERVIEW, members: [UNREADY_MEMBER], adventures: [adventure("a1", "A door in the wrong wood", "active")] },
    });

    const ready = renderApp(["/runs/ready"]);
    expect(await screen.findByText("Next up")).toBeInTheDocument();
    expect(screen.queryByText("Every player needs a character before the first adventure can start.")).not.toBeInTheDocument();
    ready.unmount();

    renderApp(["/runs/waiting"]);
    expect(await screen.findByText("Waiting on party")).toBeInTheDocument();
    expect(
      screen.getByText("Every player needs a character before the first adventure can start."),
    ).toBeInTheDocument();
  });

  it("AC3: rows after the current one read Locked, rows before it read Done", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs/abc/overview", {
      status: 200,
      body: {
        ...OVERVIEW,
        members: [READY_MEMBER],
        adventures: [
          adventure("a1", "A door in the wrong wood", "done"),
          adventure("a2", "The barrel argument", "active"),
          adventure("a3", "Debts of the landlord", "unplayed"),
        ],
      },
    });

    renderApp(["/runs/abc"]);

    await screen.findByText("Done");
    expect(screen.getByText("Next up")).toBeInTheDocument();
    expect(screen.getByText("Locked")).toBeInTheDocument();
  });

  it("AC4: Start adventure renders once, on the current row, disabled", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs/abc/overview", {
      status: 200,
      body: {
        ...OVERVIEW,
        members: [READY_MEMBER],
        adventures: [
          adventure("a1", "A door in the wrong wood", "done"),
          adventure("a2", "The barrel argument", "active"),
          adventure("a3", "Debts of the landlord", "unplayed"),
        ],
      },
    });

    renderApp(["/runs/abc"]);

    const startButtons = await screen.findAllByRole("button", { name: "Start adventure" });
    expect(startButtons).toHaveLength(1);
    expect(startButtons[0]).toBeDisabled();
  });
});
