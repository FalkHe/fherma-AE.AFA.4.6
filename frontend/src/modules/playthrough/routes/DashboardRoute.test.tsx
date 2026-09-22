// Sprint 007/07 WI1, AC1-AC5, plus HomeRoute.test.tsx's `RequireAuth`-on-`/`
// coverage, moved here now that `/` renders `DashboardRoute` (AC6). Rendered
// through the real guard via `renderApp`, so the session read it makes is
// always stubbed first.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderApp } from "../../../test/render";
import { deferredResponse, mockRoute } from "../../../test/network";

const USER = { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };

function stubAuthenticated() {
  mockRoute("GET", "/api/v1/users/me", { status: 200, body: USER, headers: { "X-CSRF-Token": "csrf-token-value" } });
}

function runSummary(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "run-a",
    campaignId: "greenhollow",
    status: "setup",
    createdAt: "2026-09-08T00:00:00.000000+00:00",
    campaignTitle: "Bogwater Assizes",
    campaignSummary: "A courtroom under a marsh. Nobody has told the defendant he is dead.",
    adventuresCompleted: 2,
    adventuresTotal: 8,
    playerCount: 3,
    unavailable: false,
    ...overrides,
  };
}

describe("DashboardRoute on / (AC1-AC5)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("the moved guard case: while the session read is pending shows a labelled spinner and no header; resolves unauthenticated to /signin", async () => {
    const pending = deferredResponse();
    mockRoute("GET", "/api/v1/users/me", () => pending.promise);

    const app = renderApp(["/"]);

    expect(screen.getByRole("progressbar", { name: /loading/i })).toBeInTheDocument();
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();

    pending.resolve({
      status: 401,
      body: { error: { code: "NOT_AUTHENTICATED", message: "Authentication required.", details: null } },
    });

    await waitFor(() => expect(app.getPathname()).toBe("/signin"));
  });

  it("AC5: renders the greeting as the one h1, focused on mount, independently of the runs query", async () => {
    stubAuthenticated();
    // Never resolves — proves the greeting doesn't wait on this query.
    mockRoute("GET", "/api/v1/playthrough/runs", () => deferredResponse().promise);

    renderApp(["/"]);

    const heading = await screen.findByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("Welcome back, thorin.");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("AC1 / AC2: one card per run, in the server's own order, with cover art, badge, teaser, the adventure/player/date line and a Begin or Resume action", async () => {
    vi.setSystemTime(new Date("2026-09-10T00:00:00.000Z"));
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", {
      status: 200,
      body: [
        runSummary({ id: "run-newer", status: "active", createdAt: "2026-09-09T00:00:00.000000+00:00" }),
        runSummary({ id: "run-older", status: "setup", createdAt: "2026-09-08T00:00:00.000000+00:00" }),
      ],
    });

    renderApp(["/"]);

    await screen.findAllByText("Bogwater Assizes");
    const links = screen.getAllByRole("link", { name: /^(begin|resume)$/i });
    expect(links).toHaveLength(2);
    // Server order kept exactly — not re-sorted by status or anything else.
    expect(links[0]).toHaveAccessibleName("Resume");
    expect(links[0]).toHaveAttribute("href", "/runs/run-newer");
    expect(links[1]).toHaveAccessibleName("Begin");
    expect(links[1]).toHaveAttribute("href", "/runs/run-older");

    expect(screen.getAllByText("New")).toHaveLength(1);
    expect(screen.getAllByText("In progress")).toHaveLength(1);
    expect(screen.getAllByText("Bogwater Assizes")).toHaveLength(2);
    expect(screen.getAllByText(/A courtroom under a marsh/)).toHaveLength(2);
    // adventuresCompleted 2 of 8 total → on adventure 3; 3 players. Relative
    // to the frozen "now" above (Intl.RelativeTimeFormat, numeric: auto),
    // run-newer (created 2026-09-09) reads "yesterday", run-older (created
    // 2026-09-08) reads "2 days ago" — proving each card computes its own
    // date rather than sharing one.
    expect(screen.getByText("Adventure 3 of 8 · 3 players · Created yesterday")).toBeInTheDocument();
    expect(screen.getByText("Adventure 3 of 8 · 3 players · Created 2 days ago")).toBeInTheDocument();
  });

  it("AC3: with no runs, the invitation card replaces the list and there is no counting subtitle", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });

    renderApp(["/"]);

    await screen.findByText("Start a new campaign");
    expect(
      screen.getByText("Pick a story, gather a party, and the Dungeon Master takes it from there."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/campaign.*waiting on you/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^(begin|resume)$/i })).not.toBeInTheDocument();
  });

  it("AC5: with runs present, the subtitle counts them", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", {
      status: 200,
      body: [runSummary({ id: "run-a" }), runSummary({ id: "run-b" })],
    });

    renderApp(["/"]);

    expect(await screen.findByText("2 campaigns are waiting on you. The lantern is still lit.")).toBeInTheDocument();
  });

  it("AC4: an unavailable run renders muted with no open action; activating it explains why and navigates nowhere", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", {
      status: 200,
      body: [
        {
          id: "run-gone",
          campaignId: "greenhollow",
          status: "archived",
          createdAt: "2026-09-08T00:00:00.000000+00:00",
          campaignTitle: null,
          campaignSummary: null,
          adventuresCompleted: 1,
          adventuresTotal: null,
          playerCount: 2,
          unavailable: true,
        },
      ],
    });

    const app = renderApp(["/"]);

    await screen.findByText("Campaign unavailable");
    expect(screen.queryByRole("link", { name: /^(begin|resume)$/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/no longer available/i)).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /why can.?t i open this/i }));

    expect(await screen.findByText(/no longer available/i)).toBeInTheDocument();
    expect(app.getPathname()).toBe("/");
  });
});
