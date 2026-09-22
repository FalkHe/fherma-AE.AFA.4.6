// Sprint 007/09 WI1, AC1-AC6: the "Select a campaign" dialog opened off
// `CampaignCta`'s "Create new campaign" button. One case per criterion,
// driven through the real dashboard via `renderApp` so the CSRF-carrying
// client and the dashboard's own `runSummaries` read are exercised exactly
// as a player would hit them. AC4/AC5's "creates nothing" is asserted
// against requests actually issued (`getRequests`), never against rendering
// alone.
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderApp } from "../../../test/render";
import { deferredResponse, getRequests, mockRoute } from "../../../test/network";

const USER = { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };

const CAMPAIGN_A = {
  id: "campaign-bogwater",
  title: "Bogwater Assizes",
  summary: "A courtroom under a marsh. Nobody has told the defendant he is dead.",
  adventureCount: 1,
};
const CAMPAIGN_B = {
  id: "campaign-kettle",
  title: "The Kettle Wars",
  summary: "Two goblin clans, one brewing recipe, and an increasingly nervous druid.",
  adventureCount: 6,
};

const RUN_A = {
  id: "run-a",
  campaignId: CAMPAIGN_A.id,
  contentVersion: "1",
  title: null,
  status: "setup",
  createdAt: "2026-09-10T00:00:00.000000+00:00",
};
const RUN_B = {
  id: "run-b",
  campaignId: CAMPAIGN_B.id,
  contentVersion: "1",
  title: null,
  status: "setup",
  createdAt: "2026-09-10T00:00:00.000000+00:00",
};

function stubAuthenticated() {
  mockRoute("GET", "/api/v1/users/me", { status: 200, body: USER, headers: { "X-CSRF-Token": "csrf-token-value" } });
}

async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Create new campaign" }));
  await screen.findByRole("heading", { name: "Select a campaign" });
  // The close button must be a sibling of `DialogTitle`, never nested
  // inside it — `Dialog`'s `aria-labelledby` points at `DialogTitle`, so an
  // `IconButton` nested there folds its own "Close" name into the dialog's.
  // `toHaveAccessibleName` checks the *whole* computed name, not a
  // substring, so a folded "Select a campaign Close" would fail this even
  // where it would not fail a plain `getByRole` name match (documented
  // gap: this still passes under jsdom's own accessible-name computation,
  // which does not fold a nested interactive descendant's name the way a
  // real browser does — the live browser check is what actually guards
  // this regression; verified live at intent review time).
  expect(screen.getByRole("dialog")).toHaveAccessibleName("Select a campaign");
}

describe("SelectCampaignDialog (AC1-AC6)", () => {
  it("AC1: lists every campaign from the catalogue with placeholder art, title, teaser and adventure count, and no tone badge", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });
    mockRoute("GET", "/api/v1/content/campaigns", { status: 200, body: [CAMPAIGN_A, CAMPAIGN_B] });

    const user = userEvent.setup();
    renderApp(["/"]);
    await openDialog(user);

    expect(screen.getAllByText("Art")).toHaveLength(2); // the shared cover-art placeholder, once per card
    expect(screen.getByText(CAMPAIGN_A.title)).toBeInTheDocument();
    expect(screen.getByText(CAMPAIGN_A.summary)).toBeInTheDocument();
    expect(screen.getByText("1 adventure")).toBeInTheDocument();
    expect(screen.getByText(CAMPAIGN_B.title)).toBeInTheDocument();
    expect(screen.getByText("6 adventures")).toBeInTheDocument();
    // `CampaignSummaryRead` carries no tone field at all, so nothing in
    // either card can render as a status/tone label.
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("AC2: choosing a campaign creates *that* campaign's run, shows the rolling-up state, then opens the run screen", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });
    // Two campaigns in the catalogue, and the second one is chosen below —
    // proving the card-to-id wiring, not just that *some* request landed
    // (a bug that always sent the first campaign's id would pass a
    // single-campaign fixture unnoticed).
    mockRoute("GET", "/api/v1/content/campaigns", { status: 200, body: [CAMPAIGN_A, CAMPAIGN_B] });
    const pending = deferredResponse();
    mockRoute("POST", "/api/v1/playthrough/campaign", () => pending.promise);

    const user = userEvent.setup();
    const app = renderApp(["/"]);
    await openDialog(user);

    const card = screen.getByRole("button", { name: new RegExp(CAMPAIGN_B.title) });
    await user.click(card);

    expect(
      await screen.findByText(`Rolling up "${CAMPAIGN_B.title}" — taking you to the table.`),
    ).toBeInTheDocument();
    expect(card).toBeDisabled();

    pending.resolve({ status: 201, body: RUN_B });

    await waitFor(() => expect(app.getPathname()).toBe(`/runs/${RUN_B.id}`));

    const postRequests = getRequests({ method: "POST", path: "/api/v1/playthrough/campaign" });
    expect(postRequests).toHaveLength(1);
    // The chosen card's id, not the catalogue's first entry.
    expect(postRequests[0].body).toEqual({ campaignId: CAMPAIGN_B.id });
    // The write reuses the one CSRF-stamping client (sprint brief) — this
    // POST carries the token the earlier GET /users/me handed it.
    expect(postRequests[0].headers["x-csrf-token"]).toBe("csrf-token-value");
  });

  it("AC3: choosing a campaign the player already has a run of neither warns nor blocks, and the dashboard afterwards shows both runs", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", [
      { status: 200, body: [] },
      { status: 200, body: [{ ...RUN_A, campaignTitle: CAMPAIGN_A.title, campaignSummary: CAMPAIGN_A.summary, adventuresCompleted: 0, adventuresTotal: 1, playerCount: 0, unavailable: false }] },
      {
        status: 200,
        body: [
          { ...RUN_A, campaignTitle: CAMPAIGN_A.title, campaignSummary: CAMPAIGN_A.summary, adventuresCompleted: 0, adventuresTotal: 1, playerCount: 0, unavailable: false },
          { ...RUN_A, id: "run-a-2", campaignTitle: CAMPAIGN_A.title, campaignSummary: CAMPAIGN_A.summary, adventuresCompleted: 0, adventuresTotal: 1, playerCount: 0, unavailable: false },
        ],
      },
    ]);
    mockRoute("GET", "/api/v1/content/campaigns", { status: 200, body: [CAMPAIGN_A] });
    mockRoute("POST", "/api/v1/playthrough/campaign", [
      { status: 201, body: RUN_A },
      { status: 201, body: { ...RUN_A, id: "run-a-2" } },
    ]);

    const user = userEvent.setup();
    const app = renderApp(["/"]);

    await openDialog(user);
    await user.click(screen.getByRole("button", { name: new RegExp(CAMPAIGN_A.title) }));
    await waitFor(() => expect(app.getPathname()).toBe("/runs/run-a"));

    app.goBack();
    await waitFor(() => expect(app.getPathname()).toBe("/"));

    await openDialog(user);
    await user.click(screen.getByRole("button", { name: new RegExp(CAMPAIGN_A.title) }));
    await waitFor(() => expect(app.getPathname()).toBe("/runs/run-a-2"));

    const postRequests = getRequests({ method: "POST", path: "/api/v1/playthrough/campaign" });
    expect(postRequests).toHaveLength(2);
    expect(postRequests[0].body).toEqual({ campaignId: CAMPAIGN_A.id });
    expect(postRequests[1].body).toEqual({ campaignId: CAMPAIGN_A.id });

    app.goBack();
    await waitFor(() => expect(app.getPathname()).toBe("/"));

    expect(await screen.findAllByRole("link", { name: /^begin$/i })).toHaveLength(2);
  });

  it("AC4: a failed creation leaves the dialog open with a retryable error and creates nothing, until retried", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });
    mockRoute("GET", "/api/v1/content/campaigns", { status: 200, body: [CAMPAIGN_A] });
    mockRoute("POST", "/api/v1/playthrough/campaign", [
      { status: 500, body: { error: { code: "UNEXPECTED", message: "boom", details: null } } },
      { status: 201, body: RUN_A },
    ]);

    const user = userEvent.setup();
    const app = renderApp(["/"]);
    await openDialog(user);

    await user.click(screen.getByRole("button", { name: new RegExp(CAMPAIGN_A.title) }));

    expect(await screen.findByText("Something went wrong. Please try again.")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveAccessibleName("Select a campaign");
    expect(app.getPathname()).toBe("/");
    expect(getRequests({ method: "POST", path: "/api/v1/playthrough/campaign" })).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Try again" }));

    await waitFor(() => expect(app.getPathname()).toBe(`/runs/${RUN_A.id}`));
    expect(getRequests({ method: "POST", path: "/api/v1/playthrough/campaign" })).toHaveLength(2);
  });

  it("AC5: dismissing the dialog creates nothing and returns to the dashboard", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });
    mockRoute("GET", "/api/v1/content/campaigns", { status: 200, body: [CAMPAIGN_A] });

    const user = userEvent.setup();
    const app = renderApp(["/"]);
    await openDialog(user);

    await user.keyboard("{Escape}");

    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Select a campaign" })).not.toBeInTheDocument(),
    );
    expect(app.getPathname()).toBe("/");
    expect(getRequests({ method: "POST", path: "/api/v1/playthrough/campaign" })).toHaveLength(0);
  });

  it("AC5: the header's close button dismisses the dialog and creates nothing", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });
    mockRoute("GET", "/api/v1/content/campaigns", { status: 200, body: [CAMPAIGN_A] });

    const user = userEvent.setup();
    const app = renderApp(["/"]);
    await openDialog(user);

    await user.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Select a campaign" })).not.toBeInTheDocument(),
    );
    expect(app.getPathname()).toBe("/");
    expect(getRequests({ method: "POST", path: "/api/v1/playthrough/campaign" })).toHaveLength(0);
  });

  it("AC6: the intro line reads 'Choose the story your party will play.' with no promise about renaming", async () => {
    stubAuthenticated();
    mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] });
    mockRoute("GET", "/api/v1/content/campaigns", { status: 200, body: [] });

    const user = userEvent.setup();
    renderApp(["/"]);
    await openDialog(user);

    expect(screen.getByText("Choose the story your party will play.")).toBeInTheDocument();
    expect(screen.queryByText(/rename/i)).not.toBeInTheDocument();
  });
});
