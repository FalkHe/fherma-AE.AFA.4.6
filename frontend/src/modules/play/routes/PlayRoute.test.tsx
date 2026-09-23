// Sprint 010/06 WI4. Behaviours: the header shows the campaign back link,
// the adventure title and the scene line, from the table read (AC2); the
// back link returns to the lobby (the run screen); loading, error and
// not-found states render; a run with no adventure yet omits those header
// lines rather than showing blanks; a narrow screen matches D12's narrow
// wireframe (AC6 — no party strip, one column, the header stacked above
// the transcript, since that strip is a later sprint's work).
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderApp } from "../../../test/render";
import { mockRoute } from "../../../test/network";

const USER = { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };

function stubAuthenticated() {
  mockRoute("GET", "/api/v1/users/me", { status: 200, body: USER, headers: { "X-CSRF-Token": "csrf-token-value" } });
}

const HERO = {
  id: "char-1",
  name: "Rosalind Thorn",
  currentHp: 12,
  maxHp: 12,
  armourClass: 15,
  race: "Human",
  characterClass: "Fighter",
  level: 1,
  abilities: { strength: 10, dexterity: 10, constitution: 10, intelligence: 10, wisdom: 10, charisma: 10 },
  appearance: "",
  backstory: "",
  items: [],
};

const TABLE = {
  runId: "run-1",
  runTitle: null,
  runStatus: "active",
  campaignTitle: "Greenhollow",
  adventure: { id: "a1", runId: "ar1", title: "Goblins of Greenhollow", status: "active" as const },
  scene: { id: "s1", name: "The Village Green" },
  heroes: [HERO],
};

function mockTable(runId: string, body: unknown) {
  mockRoute("GET", `/api/v1/playthrough/runs/${runId}/table`, { status: 200, body });
}

function mockEvents(runId: string, events: unknown[] = []) {
  mockRoute("GET", `/api/v1/playthrough/campaign/${runId}/events`, { status: 200, body: { events, awaiting: "none" } });
}

describe("PlayRoute on /runs/:runId/play (AC2, AC6, AC7)", () => {
  it("AC2: shows the campaign back link, the adventure title and the scene line, from the table read", async () => {
    stubAuthenticated();
    mockTable("run-1", TABLE);
    mockEvents("run-1");

    renderApp(["/runs/run-1/play"]);

    expect(await screen.findByRole("link", { name: "‹ Greenhollow" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Goblins of Greenhollow" })).toBeInTheDocument();
    expect(screen.getByText("The Village Green · saved as you go")).toBeInTheDocument();
  });

  it("the back link returns to the lobby (the run screen)", async () => {
    stubAuthenticated();
    mockTable("run-1", TABLE);
    mockEvents("run-1");
    mockRoute("GET", "/api/v1/playthrough/runs/run-1/overview", {
      status: 200,
      body: {
        id: "run-1",
        campaignId: "greenhollow",
        contentVersion: "v1",
        title: null,
        status: "active",
        createdAt: "2026-09-08T12:34:56.789012+00:00",
        campaignTitle: "Greenhollow",
        campaignSummary: "A pub that hides in the wood.",
        unavailable: false,
        members: [],
        adventures: [],
      },
    });

    const app = renderApp(["/runs/run-1/play"]);

    const backLink = await screen.findByRole("link", { name: "‹ Greenhollow" });
    expect(backLink).toHaveAttribute("href", "/runs/run-1");

    const user = userEvent.setup();
    await user.click(backLink);
    await waitFor(() => expect(app.getPathname()).toBe("/runs/run-1"));
  });

  it("renders a loading state while the table read is pending", async () => {
    stubAuthenticated();
    // No responder registered for the table route: the request stays
    // pending forever, exactly like an in-flight read.
    mockRoute("GET", "/api/v1/playthrough/runs/run-1/table", () => new Promise(() => {}));

    renderApp(["/runs/run-1/play"]);

    expect(await screen.findByLabelText("Loading…")).toBeInTheDocument();
  });

  it("renders an error state with a retry that recovers", async () => {
    stubAuthenticated();
    let attempts = 0;
    mockTable("run-1", TABLE);
    mockRoute("GET", "/api/v1/playthrough/runs/run-1/table", () => {
      attempts += 1;
      if (attempts === 1) {
        throw new Error("simulated network failure");
      }
      return { status: 200, body: TABLE };
    });
    mockEvents("run-1");

    renderApp(["/runs/run-1/play"]);

    const retryButton = await screen.findByRole("button", { name: "Try again" });
    expect(screen.getByText("Cannot reach the server. Check your connection and try again.")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(retryButton);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Goblins of Greenhollow");
  });

  it("renders a plain not-found message for a run that does not exist", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs/missing/table", {
      status: 404,
      body: { error: { code: "NOT_FOUND", message: "x", details: null } },
    });

    renderApp(["/runs/missing/play"]);

    expect(await screen.findByText("This run could not be found.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
  });

  it("a run with no adventure yet omits those header lines rather than showing blanks", async () => {
    stubAuthenticated();
    mockTable("run-1", { ...TABLE, adventure: null, scene: null });
    mockEvents("run-1");

    renderApp(["/runs/run-1/play"]);

    expect(await screen.findByRole("link", { name: "‹ Greenhollow" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(screen.queryByText(/saved as you go/)).not.toBeInTheDocument();
    // The empty-transcript line carries the screen instead of a blank space
    // (research.md Assumptions).
    expect(await screen.findByText("Nothing written down yet. The Dungeon Master is opening the book.")).toBeInTheDocument();
  });

  it("AC6: a narrow screen matches D12's narrow wireframe — one column, header stacked above the transcript, no party strip", async () => {
    stubAuthenticated();
    mockTable("run-1", TABLE);
    mockEvents("run-1");

    renderApp(["/runs/run-1/play"]);

    const backLink = await screen.findByRole("link", { name: "‹ Greenhollow" });
    const heading = screen.getByRole("heading", { level: 1, name: "Goblins of Greenhollow" });
    const sceneLine = screen.getByText("The Village Green · saved as you go");
    const transcript = screen.getByRole("log");

    // D12 §5's narrow layout is the header's three lines stacked, then the
    // transcript below — the same single column D12 §2 uses without a
    // party rail (excluded this sprint) beside it. `compareDocumentPosition`
    // asserts that order directly rather than guessing at a breakpoint,
    // since jsdom lays out nothing (research.md "Scrolling under test").
    expect(backLink.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(heading.compareDocumentPosition(sceneLine) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(sceneLine.compareDocumentPosition(transcript) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // No party strip — that belongs to a later sprint (work item scope).
    expect(screen.queryByText(/HP\s*\d+\s*\/\s*\d+/)).not.toBeInTheDocument();
    expect(screen.queryByText("Party")).not.toBeInTheDocument();
  });
});
