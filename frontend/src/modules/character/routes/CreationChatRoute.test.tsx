// Sprint 009-06, WI1 — AC1, AC2, AC4, AC5, AC6 (AC3 lives in
// SheetPanel.test.tsx, since it needs no route at all). Rendered through the
// real guard via `renderApp`, so the session read it makes is always
// stubbed first, matching every other route suite in this tree.
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderApp } from "../../../test/render";
import { getRequests, mockRoute } from "../../../test/network";
import character from "../../../core/i18n/locales/en/character.json";

const USER = { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };

const OVERVIEW = {
  id: "r1",
  campaignId: "greenhollow",
  contentVersion: "v1",
  title: null,
  status: "setup",
  createdAt: "2026-09-08T12:34:56.789012+00:00",
  campaignTitle: "The Rotting Stump",
  campaignSummary: "A pub that hides in the wood and only opens for people it likes.",
  unavailable: false,
  members: [{ userId: "u1", username: "thorin", role: "owner", ready: false, characterName: null }],
  adventures: [],
};

const EMPTY_SHEET = {};

function stubAuthenticated() {
  mockRoute("GET", "/api/v1/users/me", { status: 200, body: USER, headers: { "X-CSRF-Token": "csrf-token-value" } });
}

function greetingReply(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    conversationId: "conv-1",
    reply: "Well met. This campaign keeps a hero ready: Rosalind Thorn. Take her, or make your own?",
    sheet: EMPTY_SHEET,
    step: "raceClass",
    stepNumber: 1,
    canSave: false,
    saved: false,
    error: false,
    readyMadeName: "Rosalind Thorn",
    ...overrides,
  };
}

describe("CreationChatRoute on /runs/:runId/create-character (AC1, AC2, AC4-AC6)", () => {
  it("AC1: 'Create character' on the run screen opens the creation page at its own address", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs/r1/overview", { status: 200, body: OVERVIEW });
    // Mounting the destination page fires the start-creation call; stubbed
    // here even though this test only asserts the navigation itself.
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: greetingReply() });

    const app = renderApp(["/runs/r1"]);

    const createButton = await screen.findByRole("link", { name: "Create character" });
    const user = userEvent.setup();
    await user.click(createButton);

    await waitFor(() => expect(app.getPathname()).toBe("/runs/r1/create-character"));
  });

  it("AC2: the greeting renders as a Keeper turn and a choice button posts its own label", async () => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: greetingReply() });
    mockRoute("POST", "/api/v1/character/creation/conv-1/messages", {
      status: 200,
      body: greetingReply({
        reply: "A halfling rogue, then. Shall I write that down?",
        step: "raceClass",
        stepNumber: 1,
      }),
    });

    renderApp(["/runs/r1/create-character"]);

    expect(await screen.findByText(greetingReply().reply)).toBeInTheDocument();

    const takeButton = await screen.findByRole("button", { name: "Take Rosalind Thorn" });
    const user = userEvent.setup();
    await user.click(takeButton);

    await waitFor(() => expect(getRequests({ method: "POST", path: "/api/v1/character/creation/conv-1/messages" })).toHaveLength(1));
    expect(getRequests({ method: "POST", path: "/api/v1/character/creation/conv-1/messages" })[0].body).toEqual({
      text: "Take Rosalind Thorn",
    });
  });

  it("AC4: 'Back to the run' opens the leave dialog, and 'Leave' returns to the run", async () => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: greetingReply() });

    const app = renderApp(["/runs/r1/create-character"]);
    await screen.findByText(greetingReply().reply);

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Back to the run" }));

    expect(await screen.findByText("Leave character creation?")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Leave" }));

    await waitFor(() => expect(app.getPathname()).toBe("/runs/r1"));
  });

  it("AC5: an error reply shows the in-voice line and 'Try again' re-posts the same text", async () => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: greetingReply() });
    mockRoute("POST", "/api/v1/character/creation/conv-1/messages", [
      { status: 200, body: greetingReply({ error: true, reply: character.chat.error }) },
      { status: 200, body: greetingReply({ reply: "Understood. Shall I write that down?" }) },
    ]);

    renderApp(["/runs/r1/create-character"]);
    await screen.findByText(greetingReply().reply);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(character.chat.placeholder), "a sneaky halfling burglar");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(character.chat.error)).toBeInTheDocument();
    const retryButton = await screen.findByRole("button", { name: "Try again" });

    await user.click(retryButton);

    await waitFor(() => expect(screen.getByText("Understood. Shall I write that down?")).toBeInTheDocument());
    const messageRequests = getRequests({ method: "POST", path: "/api/v1/character/creation/conv-1/messages" });
    expect(messageRequests).toHaveLength(2);
    expect(messageRequests[0].body).toEqual({ text: "a sneaky halfling burglar" });
    expect(messageRequests[1].body).toEqual({ text: "a sneaky halfling burglar" });
    // The retry re-sent the request but must not have appended a second
    // player turn to the transcript.
    expect(screen.getAllByText("a sneaky halfling burglar")).toHaveLength(1);
  });

  it("AC6: the page's visible copy matches character.json — no raw translation key ever renders", async () => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: greetingReply() });

    renderApp(["/runs/r1/create-character"]);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(character.chat.title);
    expect(screen.getByText(character.chat.subtitle)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: character.chat.back })).toBeInTheDocument();
    expect(screen.getByText(character.chat.keeper)).toBeInTheDocument();
    expect(screen.getByLabelText(character.chat.placeholder)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: character.chat.send })).toBeInTheDocument();

    expect(screen.queryByText(/chat\.\w+/)).not.toBeInTheDocument();
    expect(screen.queryByText(/character:/)).not.toBeInTheDocument();
  });
});
