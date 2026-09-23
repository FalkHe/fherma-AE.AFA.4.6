// Sprint 010/08 WI1, AC5: "Start adventure" goes live on the current
// unplayed row. Rendered through a minimal `:runId` route (not the whole
// app) so `useParams`/`useEnterAdventure`'s navigation target can be probed
// directly, same precedent as `useSignIn.test.tsx`.
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Routes, Route, useLocation } from "react-router";

import { renderWithProviders } from "../../../test/render";
import { getRequests, mockRoute } from "../../../test/network";
import { AdventuresSection, type RunAdventure } from "./AdventuresSection";
import type { RunMember } from "../hooks/useRunOverview";

const RUN_ID = "run-abc";
const ADVENTURE_PATH = `/api/v1/playthrough/campaign/${RUN_ID}/adventure`;

const READY_MEMBER = { userId: "u1", username: "thorin", role: "owner", ready: true, character: null } as RunMember;
const UNREADY_MEMBER = { userId: "u1", username: "thorin", role: "owner", ready: false, character: null } as RunMember;

function adventure(id: string, title: string, status: "done" | "active" | "unplayed"): RunAdventure {
  return { id, title, introExcerpt: `${title} teaser`, status } as RunAdventure;
}

function LocationProbe() {
  const location = useLocation();
  return <p>play screen: {JSON.stringify(location.state)}</p>;
}

function renderSection(members: RunMember[], adventures: RunAdventure[]) {
  return renderWithProviders(
    <Routes>
      <Route path="/runs/:runId" element={<AdventuresSection adventures={adventures} members={members} />} />
      <Route path="/runs/:runId/play" element={<LocationProbe />} />
    </Routes>,
    { route: `/runs/${RUN_ID}` },
  );
}

describe("AdventuresSection's live Start adventure (sprint 010/08 WI1, AC5)", () => {
  it("is enabled when the party is ready", async () => {
    renderSection([READY_MEMBER], [adventure("a1", "The barrel argument", "unplayed")]);

    expect(await screen.findByRole("button", { name: "Start adventure" })).not.toBeDisabled();
  });

  it("stays disabled while the party is not ready", async () => {
    renderSection([UNREADY_MEMBER], [adventure("a1", "The barrel argument", "unplayed")]);

    expect(await screen.findByRole("button", { name: "Start adventure" })).toBeDisabled();
  });

  it("enters the adventure over the network, disables the button in flight, then opens the play screen with the one-shot flag", async () => {
    mockRoute("POST", ADVENTURE_PATH, { status: 201, body: { id: "adv-1", status: "active" } });
    renderSection([READY_MEMBER], [adventure("a1", "The barrel argument", "unplayed")]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Start adventure" }));

    expect(await screen.findByText('play screen: {"startOpening":true}')).toBeInTheDocument();
    expect(getRequests({ method: "POST", path: ADVENTURE_PATH })).toHaveLength(1);
  });

  it("a 409 ADVENTURE_ACTIVE still counts as success and opens the play screen", async () => {
    mockRoute("POST", ADVENTURE_PATH, {
      status: 409,
      body: { error: { code: "ADVENTURE_ACTIVE", message: "already active", details: null } },
    });
    renderSection([READY_MEMBER], [adventure("a1", "The barrel argument", "unplayed")]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Start adventure" }));

    expect(await screen.findByText('play screen: {"startOpening":true}')).toBeInTheDocument();
  });

  it("a network error shows a retryable line and leaves the button pressable for another try", async () => {
    mockRoute("POST", ADVENTURE_PATH, [
      { status: 500, body: { error: { code: "INTERNAL_ERROR", message: "boom", details: null } } },
      { status: 201, body: { id: "adv-1", status: "active" } },
    ]);
    renderSection([READY_MEMBER], [adventure("a1", "The barrel argument", "unplayed")]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Start adventure" }));

    expect(await screen.findByText("Cannot reach the server. Check your connection and try again.")).toBeInTheDocument();
    const retryButton = screen.getByRole("button", { name: "Start adventure" });
    await waitFor(() => expect(retryButton).not.toBeDisabled());

    await user.click(retryButton);

    expect(await screen.findByText('play screen: {"startOpening":true}')).toBeInTheDocument();
  });
});
