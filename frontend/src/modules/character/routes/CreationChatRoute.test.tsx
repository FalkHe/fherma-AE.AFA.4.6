// Sprint 009-06, WI1 — AC1, AC2, AC4, AC5, AC6 (AC3 lives in
// SheetPanel.test.tsx, since it needs no route at all). Rendered through the
// real guard via `renderApp`, so the session read it makes is always
// stubbed first, matching every other route suite in this tree.
//
// Sprint 009-07, WI1 — the review/save describe block below. Every
// assertion on the review's own copy is scoped with `within` against the
// panel's own `aria-label={review.title}` region. Since the creation-chat
// viewport fix the review is a full-width sheet with the sheet rail dropped,
// and a value can repeat across cells (CON 14, armour class 14), so AC1
// reads each labelled value off its own `dt`'s `dd`s rather than matching
// bare text anywhere in the region.
import { StrictMode } from "react";
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../../../App";
import { renderApp, renderWithProviders } from "../../../test/render";
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
  members: [{ userId: "u1", username: "thorin", role: "owner", ready: false, character: null }],
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

  it("under StrictMode the conversation starts once, so the greeting shows once", async () => {
    // `main.tsx` mounts the app in `StrictMode`, which in development runs
    // every mount effect twice (mount, simulated unmount, remount). The
    // shared test renderer leaves `StrictMode` out, so this case opts back
    // in: the start call must still go out exactly once, or the keeper's
    // greeting lands in the transcript twice.
    stubAuthenticated();
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: greetingReply() });

    renderWithProviders(
      <StrictMode>
        <App />
      </StrictMode>,
      { route: "/runs/r1/create-character" },
    );

    await waitFor(() => expect(screen.getAllByText(greetingReply().reply)).toHaveLength(1));
    // Settle any effects that might still be in flight before counting.
    await waitFor(() => expect(getRequests({ method: "POST", path: "/api/v1/character/runs/r1/creation" })).toHaveLength(1));
    expect(screen.getAllByText("Tavern Keeper")).toHaveLength(1);
    expect(screen.getAllByText(greetingReply().reply)).toHaveLength(1);
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

const FULL_SHEET = {
  name: "Pip Underbough",
  race: "Halfling",
  characterClass: "Rogue",
  level: 1,
  alignment: "Chaotic Good",
  abilities: { strength: 8, dexterity: 16, constitution: 14, intelligence: 12, wisdom: 10, charisma: 13 },
  maxHp: 9,
  armourClass: 14,
  speed: 25,
  skills: ["Stealth", "Sleight of Hand"],
  equipment: ["Rapier", "Leather armour"],
  appearance: "Barely three feet of him, all elbows and grin.",
  backstory: "Raised in the kitchens of a river inn.",
};

function reviewReply(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    conversationId: "conv-1",
    reply: "That's everyone. Here's Pip Underbough, ready to walk in.",
    sheet: FULL_SHEET,
    step: "review",
    stepNumber: 7,
    canSave: true,
    saved: false,
    error: false,
    readyMadeName: null,
    ...overrides,
  };
}

/** The `dd`s that follow the `dt` labelled `label`, up to the next `dt`. */
function definitionsOf(region: HTMLElement, label: string): HTMLElement[] {
  const term = within(region).getByText(label, { selector: "dt" });
  const definitions: HTMLElement[] = [];
  let next = term.nextElementSibling;
  while (next && next.tagName === "DD") {
    definitions.push(next as HTMLElement);
    next = next.nextElementSibling;
  }
  return definitions;
}

function valuesOf(region: HTMLElement, label: string): string[] {
  return definitionsOf(region, label).map((definition) => definition.textContent ?? "");
}

function findReviewRegion() {
  return screen.findByRole("region", { name: character.review.title });
}

describe("CreationChatRoute's review and save (sprint 009-07, WI1, AC1-AC3, AC5-AC6)", () => {
  it("AC1: a review reply renders every field of the finished sheet and both buttons", async () => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: reviewReply() });

    renderApp(["/runs/r1/create-character"]);

    const region = await findReviewRegion();
    const scoped = within(region);

    expect(scoped.getByRole("heading", { name: "Pip Underbough" })).toBeInTheDocument();
    // Race, class, level and alignment share the identity line.
    expect(scoped.getByText("Halfling Rogue · Level 1 · Chaotic Good")).toBeInTheDocument();

    expect(valuesOf(region, "Hit points")).toEqual(["9"]);
    expect(valuesOf(region, "Armour class")).toEqual(["14"]);
    expect(valuesOf(region, "Speed")).toEqual(["25"]);
    expect(valuesOf(region, "STR")).toEqual(["8", "−1"]);
    expect(valuesOf(region, "DEX")).toEqual(["16", "+3"]);
    expect(valuesOf(region, "CON")).toEqual(["14", "+2"]);
    expect(valuesOf(region, "INT")).toEqual(["12", "+1"]);
    expect(valuesOf(region, "WIS")).toEqual(["10", "+0"]);
    expect(valuesOf(region, "CHA")).toEqual(["13", "+1"]);

    const [skills] = definitionsOf(region, "Skills");
    expect(within(skills).getByText("Stealth")).toBeInTheDocument();
    expect(within(skills).getByText("Sleight of Hand")).toBeInTheDocument();
    const [equipment] = definitionsOf(region, "Equipment");
    expect(within(equipment).getByText("Rapier")).toBeInTheDocument();
    expect(within(equipment).getByText("Leather armour")).toBeInTheDocument();
    expect(valuesOf(region, "Looks")).toEqual([FULL_SHEET.appearance]);
    expect(valuesOf(region, "Story")).toEqual([FULL_SHEET.backstory]);

    expect(scoped.getByRole("button", { name: character.review.save })).toBeInTheDocument();
    expect(scoped.getByRole("button", { name: character.review.change })).toBeInTheDocument();
  });

  it("AC2: 'Change something' posts its own text and brings the transcript back; 'Looks right, save' posts its own text", async () => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: reviewReply() });
    mockRoute("POST", "/api/v1/character/creation/conv-1/messages", {
      status: 200,
      body: reviewReply({ reply: "What would you like to change?" }),
    });

    const app = renderApp(["/runs/r1/create-character"]);
    await findReviewRegion();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: character.review.change }));

    expect(screen.queryByRole("region", { name: character.review.title })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(character.review.change)).toBeInTheDocument());
    expect(screen.getByLabelText(character.chat.placeholder)).toBeInTheDocument();

    await waitFor(() =>
      expect(getRequests({ method: "POST", path: "/api/v1/character/creation/conv-1/messages" })).toHaveLength(1),
    );
    expect(getRequests({ method: "POST", path: "/api/v1/character/creation/conv-1/messages" })[0].body).toEqual({
      text: "Change something",
    });

    app.unmount();

    stubAuthenticated();
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: reviewReply() });
    mockRoute("POST", "/api/v1/character/creation/conv-1/messages", { status: 200, body: reviewReply({ saved: false }) });

    renderApp(["/runs/r1/create-character"]);
    await findReviewRegion();

    await user.click(screen.getByRole("button", { name: character.review.save }));

    await waitFor(() =>
      expect(getRequests({ method: "POST", path: "/api/v1/character/creation/conv-1/messages" })).toHaveLength(2),
    );
    expect(getRequests({ method: "POST", path: "/api/v1/character/creation/conv-1/messages" })[1].body).toEqual({
      text: "Looks right, save",
    });
  });

  it("after 'Change something', the keeper's answer to the change stays on screen while the backend still reports the review", async () => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: reviewReply() });
    // The real backend stays at `review`/`canSave` through the whole change round.
    mockRoute("POST", "/api/v1/character/creation/conv-1/messages", [
      { status: 200, body: reviewReply({ reply: "What would you like to change?" }) },
      { status: 200, body: reviewReply({ reply: "Pip is older now, with grey at the temples." }) },
    ]);

    renderApp(["/runs/r1/create-character"]);
    await findReviewRegion();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: character.review.change }));
    await screen.findByText("What would you like to change?");

    await user.type(screen.getByLabelText(character.chat.placeholder), "Make him older{Enter}");

    expect(await screen.findByText("Pip is older now, with grey at the temples.")).toBeInTheDocument();
    expect(getRequests({ method: "POST", path: "/api/v1/character/creation/conv-1/messages" })[1].body).toEqual({
      text: "Make him older",
    });
    expect(screen.queryByRole("region", { name: character.review.title })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: character.review.back }));

    expect(await findReviewRegion()).toBeInTheDocument();
    // Going back to the review is a view switch — it sends nothing.
    expect(getRequests({ method: "POST", path: "/api/v1/character/creation/conv-1/messages" })).toHaveLength(2);
  });

  it("after 'Change something', a change that leaves the review step re-opens the review on its own once it is reached again", async () => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: reviewReply() });
    mockRoute("POST", "/api/v1/character/creation/conv-1/messages", [
      { status: 200, body: reviewReply({ reply: "What would you like to change?" }) },
      { status: 200, body: reviewReply({ reply: "A bard, then. Which two skills?", step: "skills", stepNumber: 5, canSave: false }) },
      { status: 200, body: reviewReply({ reply: "That's everyone again." }) },
    ]);

    renderApp(["/runs/r1/create-character"]);
    await findReviewRegion();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: character.review.change }));
    await screen.findByText("What would you like to change?");

    await user.type(screen.getByLabelText(character.chat.placeholder), "Make him a bard{Enter}");
    await screen.findByText("A bard, then. Which two skills?");
    expect(screen.queryByRole("button", { name: character.review.back })).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(character.chat.placeholder), "Performance and Persuasion{Enter}");

    expect(await findReviewRegion()).toBeInTheDocument();
  });

  it("AC3: a saved:true reply lands on /runs/r1 and a second overview GET is recorded", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs/r1/overview", [
      { status: 200, body: OVERVIEW },
      { status: 200, body: { ...OVERVIEW, members: [{ userId: "u1", username: "thorin", role: "owner", ready: true, character: null }] } },
    ]);
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: reviewReply() });
    mockRoute("POST", "/api/v1/character/creation/conv-1/messages", {
      status: 200,
      body: reviewReply({ saved: true, reply: "Written down. Off you go." }),
    });

    const app = renderApp(["/runs/r1"]);

    const createButton = await screen.findByRole("link", { name: "Create character" });
    const user = userEvent.setup();
    await user.click(createButton);

    await waitFor(() => expect(app.getPathname()).toBe("/runs/r1/create-character"));
    await findReviewRegion();

    await user.click(screen.getByRole("button", { name: character.review.save }));

    await waitFor(() => expect(app.getPathname()).toBe("/runs/r1"));
    await waitFor(() =>
      expect(getRequests({ method: "GET", path: "/api/v1/playthrough/runs/r1/overview" })).toHaveLength(2),
    );
  });

  it("AC5: an error:true reply to the save keeps the review on screen with the in-voice line", async () => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: reviewReply() });
    mockRoute("POST", "/api/v1/character/creation/conv-1/messages", {
      status: 200,
      body: reviewReply({ error: true, reply: character.chat.error }),
    });

    renderApp(["/runs/r1/create-character"]);
    await findReviewRegion();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: character.review.save }));

    expect(await screen.findByText(character.chat.error)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: character.review.title })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: character.review.save })).toBeInTheDocument();
  });

  it("AC6: the review's copy equals the values in character.json", async () => {
    stubAuthenticated();
    mockRoute("POST", "/api/v1/character/runs/r1/creation", { status: 201, body: reviewReply() });

    renderApp(["/runs/r1/create-character"]);

    const region = await findReviewRegion();
    expect(within(region).getByRole("heading", { name: character.review.title })).toBeInTheDocument();
    expect(within(region).getByText(character.review.subtitle)).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: character.review.save })).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: character.review.change })).toBeInTheDocument();

    expect(screen.queryByText(/review\.\w+/)).not.toBeInTheDocument();
  });
});
