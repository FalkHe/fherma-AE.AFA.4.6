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

  it("AC2 / AC4 (sprint 007/08): an active run files under In progress, which is the opening tag, with cover art, badge, teaser and a Resume action; the New card stays hidden", async () => {
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

    const links = await screen.findAllByRole("link", { name: /^(begin|resume)$/i });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAccessibleName("Resume");
    expect(links[0]).toHaveAttribute("href", "/runs/run-newer");

    expect(screen.getByRole("button", { name: "In progress" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "New" })).toHaveAttribute("aria-pressed", "false");

    // adventuresCompleted 2 of 8 total → on adventure 3; 3 players; relative
    // to the frozen "now" above (Intl.RelativeTimeFormat, numeric: auto)
    // run-newer (created 2026-09-09) reads "yesterday" — proving the visible
    // card computes its own date.
    expect(screen.getByText("Adventure 3 of 8 · 3 players · Created yesterday")).toBeInTheDocument();
    expect(screen.queryByText(/Created 2 days ago/)).not.toBeInTheDocument();
  });

  it("AC4 (sprint 007/08): with nothing in progress, the dashboard opens on New", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", {
      status: 200,
      body: [runSummary({ id: "run-new", status: "setup" })],
    });

    renderApp(["/"]);

    const link = await screen.findByRole("link", { name: /^(begin|resume)$/i });
    expect(link).toHaveAccessibleName("Begin");
    expect(screen.getByRole("button", { name: "New" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "In progress" })).toHaveAttribute("aria-pressed", "false");
  });

  it("AC1 (sprint 007/08): switching a tag filters the list", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", {
      status: 200,
      body: [
        runSummary({ id: "run-active", status: "active", campaignTitle: "Bogwater Assizes" }),
        runSummary({ id: "run-new", status: "setup", campaignTitle: "Greenhollow Woods" }),
        runSummary({ id: "run-archived", status: "archived", campaignTitle: "Sunken Keep" }),
      ],
    });

    const user = userEvent.setup();
    renderApp(["/"]);

    await screen.findByText("Bogwater Assizes");
    expect(screen.queryByText("Greenhollow Woods")).not.toBeInTheDocument();
    expect(screen.queryByText("Sunken Keep")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "New" }));
    expect(await screen.findByText("Greenhollow Woods")).toBeInTheDocument();
    expect(screen.queryByText("Bogwater Assizes")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Archived" }));
    expect(await screen.findByText("Sunken Keep")).toBeInTheDocument();
    expect(screen.queryByText("Greenhollow Woods")).not.toBeInTheDocument();
  });

  it("AC3 (sprint 007/08): an archived run's card is muted with no open action, and the note above the list says runs are kept and view-only with no mention of unarchiving", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", {
      status: 200,
      body: [runSummary({ id: "run-archived", status: "archived", campaignTitle: "Sunken Keep" })],
    });

    const user = userEvent.setup();
    renderApp(["/"]);

    // No in-progress run exists, so the dashboard opens on New (AC4), which
    // is empty — switch to Archived to see the card.
    await user.click(await screen.findByRole("button", { name: "Archived" }));

    await screen.findByText("Sunken Keep");
    expect(screen.queryByRole("link", { name: /^(begin|resume)$/i })).not.toBeInTheDocument();

    const note = screen.getByText("Archived runs are kept as they are and are view-only.");
    expect(note).toBeInTheDocument();
    expect(screen.queryByText(/unarchive/i)).not.toBeInTheDocument();
  });

  it("an empty tag shows its own 'nothing here' line instead of an empty list", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", {
      status: 200,
      body: [runSummary({ id: "run-active", status: "active", campaignTitle: "Bogwater Assizes" })],
    });

    const user = userEvent.setup();
    renderApp(["/"]);

    await screen.findByText("Bogwater Assizes");
    await user.click(screen.getByRole("button", { name: "Archived" }));

    expect(await screen.findByText("Nothing here yet.")).toBeInTheDocument();
    expect(screen.queryByText("Bogwater Assizes")).not.toBeInTheDocument();
  });

  it("AC1/AC4 (sprint 007/08): with no runs, the invitation card replaces the list, there is no counting subtitle and no tags render", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });

    renderApp(["/"]);

    await screen.findByText("Start a new campaign");
    expect(
      screen.getByText("Pick a story, gather a party, and the Dungeon Master takes it from there."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/campaign.*waiting on you/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^(begin|resume)$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Filter campaigns by status" })).not.toBeInTheDocument();
    expect(screen.queryByText("My campaigns")).not.toBeInTheDocument();
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
    const user = userEvent.setup();

    // Only an archived run exists, so the dashboard opens on New (empty)
    // — switch to Archived to see it (sprint 007/08 WI1, AC4).
    await user.click(await screen.findByRole("button", { name: "Archived" }));

    await screen.findByText("Campaign unavailable");
    expect(screen.queryByRole("link", { name: /^(begin|resume)$/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/no longer available/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /why can.?t i open this/i }));

    expect(await screen.findByText(/no longer available/i)).toBeInTheDocument();
    expect(app.getPathname()).toBe("/");
  });
});
