// Sprint 010/06 WI4. Behaviours: the header shows the campaign back link,
// the adventure title and the scene line, from the table read (AC2); the
// back link returns to the lobby (the run screen); loading, error and
// not-found states render; a run with no adventure yet omits those header
// lines rather than showing blanks; a narrow screen matches D12's narrow
// wireframe (AC6 — no party strip, one column, the header stacked above
// the transcript, since that strip is a later sprint's work).
//
// AC5's structure (verification round 1, defect 1): jsdom lays nothing out,
// so `scrollHeight`/`clientHeight`/`scrollTop` cannot be exercised
// honestly here (`useStickToLatest.test.tsx` already does that against a
// bare `div` with hand-set metrics) — this only checks the actual styling
// rules a browser would then use to lay it out: the transcript's own
// scrolling element is `overflow-y: auto`, and somewhere between it and
// the app root, a real, viewport-relative height (not a bare `"auto"` or a
// `"100%"` against an auto-height ancestor, ← the bug) is what bounds it.
// A regression back to the old `maxHeight: "100%"` chain would fail this
// exact assertion while still passing every jsdom-scroll test that mocks
// its own metrics, which is why those don't already catch it.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { I18nextProvider } from "react-i18next";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, type InitialEntry } from "react-router";

import { renderApp } from "../../../test/render";
import { getRequests, mockRoute } from "../../../test/network";
import { theme } from "../../../core/theme";
import i18n from "../../../core/i18n";
import { createQueryClient } from "../../../core/queryClient";
import App from "../../../App";

// Sprint 010/08 WI4, I5 ← the opening turn's one-shot trigger. `renderApp`
// (`test/render.tsx`) only ever accepts plain path strings, since no test
// before this one needed router *state* on the initial entry -- the flag
// this sprint reads (`useEnterAdventure.ts`'s `{ startOpening: true }`)
// lives there. Reproduces that helper's own provider stack (same file,
// "Reproduces the provider stack") rather than widening its shared
// signature for this one work item's own single caller.
function renderAppAt(initialEntries: InitialEntry[]) {
  return render(
    <ThemeProvider theme={theme} noSsr defaultMode="dark">
      <CssBaseline />
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={createQueryClient()}>
          <MemoryRouter initialEntries={initialEntries}>
            <App />
          </MemoryRouter>
        </QueryClientProvider>
      </I18nextProvider>
    </ThemeProvider>,
  );
}

// Sprint 010/07 WI6, I6 ← AC1/AC2/AC3/AC4. `PlayScreen` now mounts
// `useRunNotices`, which opens a real `EventSource` -- jsdom has none, so
// this stands in for it exactly like `useRunNotices.test.tsx`'s own fake.
// Instances are kept (sprint 010/07 WI7 round 2, ← AC2) so a test can reach
// back into the one `PlayScreen` opened and drive its `onmessage` directly,
// the same way `useRunNotices.test.tsx` drives its own fake.
class FakeEventSource {
  static readonly CLOSED = 2;
  readonly CLOSED = FakeEventSource.CLOSED;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close(): void {}
  addEventListener(): void {}
  removeEventListener(): void {}

  constructor() {
    eventSources.push(this);
  }
}

let eventSources: FakeEventSource[] = [];

beforeEach(() => {
  eventSources = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

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

  // Defect B: the table read (`usePlayTable.ts`) is fetched once and never
  // invalidated by a turn settling, so it cannot be this header's only
  // source of truth for the current scene -- the transcript's own
  // `scene_entered` rows (`divider`, `transcript.ts`) are kept live already
  // (every turn settle re-reads it) and are read here in preference to it.
  it("the scene line follows the transcript's own latest scene marker, not only the table read", async () => {
    stubAuthenticated();
    mockTable("run-1", TABLE);
    mockRoute("GET", "/api/v1/playthrough/campaign/run-1/events", {
      status: 200,
      body: {
        events: [
          { id: "e1", type: "scene_entered", turnId: "t1", payload: { adventureRunId: "ar1", sceneId: "s1", sceneTitle: "The Village Green" }, createdAt: "2026-09-08T21:00:00+00:00" },
          { id: "e2", type: "narration", turnId: "t2", payload: { text: "You push through the reeds." }, createdAt: "2026-09-08T21:01:00+00:00" },
          { id: "e3", type: "scene_entered", turnId: "t2", payload: { adventureRunId: "ar1", sceneId: "s2", sceneTitle: "The Lair Maw" }, createdAt: "2026-09-08T21:02:00+00:00" },
        ],
        awaiting: "none",
      },
    });

    renderApp(["/runs/run-1/play"]);

    expect(await screen.findByText("The Lair Maw · saved as you go")).toBeInTheDocument();
    expect(screen.queryByText("The Village Green · saved as you go")).not.toBeInTheDocument();
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

  it("AC5: the transcript scrolls itself, bounded by a real viewport-relative height rather than a bare percentage (verification round 1, defect 1)", async () => {
    stubAuthenticated();
    mockTable("run-1", TABLE);
    mockEvents("run-1");

    renderApp(["/runs/run-1/play"]);

    const transcript = await screen.findByRole("log");
    expect(getComputedStyle(transcript).overflowY).toBe("auto");

    // Walk up from the transcript looking for the ancestor that actually
    // bounds it: the old bug was every ancestor reading `"auto"` (content-
    // driven) or `"100%"` (against one of those), so a real fix must show
    // up as some concrete, viewport-relative value before the app root.
    let el: HTMLElement | null = transcript;
    const heights: string[] = [];
    while (el && el !== document.body) {
      heights.push(getComputedStyle(el).height);
      el = el.parentElement;
    }

    expect(heights.some((height) => height.includes("vh"))).toBe(true);
  });

  it("AC1: sending words shows the player row at once and the composer closes with the turn-running line", async () => {
    stubAuthenticated();
    mockTable("run-1", TABLE);
    mockEvents("run-1");
    // Left pending on purpose: this checks the state right after send, before
    // any settle -- the mutation never needs to resolve for this assertion.
    mockRoute("POST", "/api/v1/game/runs/run-1/turn", () => new Promise(() => {}));

    renderApp(["/runs/run-1/play"]);

    const input = await screen.findByLabelText("What do you do?");
    const user = userEvent.setup();
    await user.type(input, "I open the door.");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("I open the door.")).toBeInTheDocument();
    expect(screen.getByText("Rosalind Thorn")).toBeInTheDocument();
    expect(screen.getByText("The Dungeon Master has the floor.")).toBeInTheDocument();
    expect(screen.queryByLabelText("What do you do?")).not.toBeInTheDocument();
  });

  it("AC4: a mid-turn transcript (awaiting none, last event not a narration) shows the thinking line and keeps the composer closed", async () => {
    stubAuthenticated();
    mockTable("run-1", TABLE);
    mockRoute("GET", "/api/v1/playthrough/campaign/run-1/events", {
      status: 200,
      body: {
        events: [
          { id: "e1", type: "player_action", turnId: "t1", payload: { text: "I attack." }, createdAt: "2026-09-08T21:02:00+00:00" },
        ],
        awaiting: "none",
      },
    });

    renderApp(["/runs/run-1/play"]);

    expect(await screen.findByText("The Dungeon Master is thinking…")).toBeInTheDocument();
    expect(screen.getByText("The Dungeon Master has the floor.")).toBeInTheDocument();
    expect(screen.queryByLabelText("What do you do?")).not.toBeInTheDocument();
  });

  it("AC3: a transcript ending in narration (awaiting none) shows no thinking line and reopens the composer", async () => {
    stubAuthenticated();
    mockTable("run-1", TABLE);
    mockRoute("GET", "/api/v1/playthrough/campaign/run-1/events", {
      status: 200,
      body: {
        events: [
          { id: "e1", type: "narration", turnId: "t1", payload: { text: "The door creaks open." }, createdAt: "2026-09-08T21:02:00+00:00" },
        ],
        awaiting: "none",
      },
    });

    renderApp(["/runs/run-1/play"]);

    expect(await screen.findByLabelText("What do you do?")).toBeInTheDocument();
    expect(screen.queryByText("The Dungeon Master is thinking…")).not.toBeInTheDocument();
    expect(screen.queryByText("The Dungeon Master has the floor.")).not.toBeInTheDocument();
  });

  it("AC2: an 'updated' notice off the stream re-reads the transcript", async () => {
    stubAuthenticated();
    mockTable("run-1", TABLE);
    mockEvents("run-1");

    renderApp(["/runs/run-1/play"]);

    await screen.findByRole("heading", { level: 1, name: "Goblins of Greenhollow" });
    expect(eventSources).toHaveLength(1);
    const before = getRequests({ method: "GET", path: "/api/v1/playthrough/campaign/run-1/events" }).length;

    eventSources[0].onmessage?.({ data: JSON.stringify({ type: "updated", id: "evt-1" }) } as MessageEvent);

    await waitFor(() =>
      expect(
        getRequests({ method: "GET", path: "/api/v1/playthrough/campaign/run-1/events" }).length,
      ).toBeGreaterThan(before),
    );
  });

  it("AC4: landing with the router flag fires the opening turn once, thinking line shown, composer closed", async () => {
    stubAuthenticated();
    mockTable("run-1", TABLE);
    mockEvents("run-1");
    // Left pending on purpose, same precedent as the AC1 "sending" test above
    // -- this only checks the in-flight state, the mutation never needs to
    // settle for it.
    mockRoute("POST", "/api/v1/game/runs/run-1/turn", () => new Promise(() => {}));

    renderAppAt([{ pathname: "/runs/run-1/play", state: { startOpening: true } }]);

    await waitFor(() =>
      expect(getRequests({ method: "POST", path: "/api/v1/game/runs/run-1/turn" })).toHaveLength(1),
    );
    expect(getRequests({ method: "POST", path: "/api/v1/game/runs/run-1/turn" })[0].body).toEqual({ text: null });
    expect(await screen.findByText("The Dungeon Master has the floor.")).toBeInTheDocument();
    expect(screen.queryByLabelText("What do you do?")).not.toBeInTheDocument();
  });

  it("shows choice buttons for a pending question; clicking one sends it as the player's own words ← I6", async () => {
    stubAuthenticated();
    mockTable("run-1", TABLE);
    mockRoute("GET", "/api/v1/playthrough/campaign/run-1/events", {
      status: 200,
      body: {
        events: [
          {
            id: "e1",
            type: "question",
            turnId: "t1",
            payload: { text: "Fight or flee?", options: ["Fight", "Flee"] },
            createdAt: "2026-09-08T21:02:00+00:00",
          },
        ],
        awaiting: "answer:e1",
      },
    });
    mockRoute("POST", "/api/v1/game/runs/run-1/turn", () => new Promise(() => {}));

    renderApp(["/runs/run-1/play"]);

    expect(await screen.findByRole("button", { name: "Fight" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Flee" })).toBeInTheDocument();
    expect(screen.getByText("The Dungeon Master is waiting on one of those.")).toBeInTheDocument();
    expect(screen.queryByText("The Dungeon Master is thinking…")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("What do you do?")).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Flee" }));

    expect(await screen.findByText("Flee")).toBeInTheDocument();
    expect(getRequests({ method: "POST", path: "/api/v1/game/runs/run-1/turn" })).toEqual([
      expect.objectContaining({ body: { text: "Flee" } }),
    ]);
    expect(screen.queryByRole("button", { name: "Fight" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Flee" })).not.toBeInTheDocument();
    expect(screen.getByText("The Dungeon Master has the floor.")).toBeInTheDocument();
  });

  it("shows one roll button for a pending roll; clicking it asks the server to roll ← I6", async () => {
    stubAuthenticated();
    mockTable("run-1", TABLE);
    mockRoute("GET", "/api/v1/playthrough/campaign/run-1/events", {
      status: 200,
      body: {
        events: [
          {
            id: "e1",
            type: "roll_requested",
            turnId: "t1",
            payload: { formula: "1d20+3", context: { ability: "Dexterity" } },
            createdAt: "2026-09-08T21:02:00+00:00",
          },
        ],
        awaiting: "roll:e1",
      },
    });
    mockRoute("POST", "/api/v1/game/runs/run-1/turn", () => new Promise(() => {}));

    renderApp(["/runs/run-1/play"]);

    const rollButton = await screen.findByRole("button", { name: /1d20\+3/ });
    expect(screen.getAllByRole("button", { name: /1d20\+3/ })).toHaveLength(1);
    expect(screen.getByText("The dice go first.")).toBeInTheDocument();
    expect(screen.queryByLabelText("What do you do?")).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(rollButton);

    expect(getRequests({ method: "POST", path: "/api/v1/game/runs/run-1/turn" })).toEqual([
      expect.objectContaining({ body: { text: null } }),
    ]);
    await waitFor(() => expect(screen.queryByRole("button", { name: /1d20\+3/ })).not.toBeInTheDocument());
    expect(screen.getByText("The Dungeon Master has the floor.")).toBeInTheDocument();
  });

  it("landing without the router flag posts no opening turn", async () => {
    stubAuthenticated();
    mockTable("run-1", TABLE);
    mockEvents("run-1");

    renderAppAt(["/runs/run-1/play"]);

    await screen.findByRole("heading", { level: 1, name: "Goblins of Greenhollow" });
    expect(getRequests({ method: "POST", path: "/api/v1/game/runs/run-1/turn" })).toHaveLength(0);
  });
});
