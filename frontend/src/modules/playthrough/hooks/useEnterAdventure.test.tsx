// Sprint 010/08 WI1, I1/AC5: entering the current adventure over the
// network. Exercised directly against the hook (no route component
// involved beyond a probe that prints the landed location's state), same
// precedent as `useSignIn.test.tsx`.
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useLocation } from "react-router";

import { createQueryClient } from "../../../core/queryClient";
import { mockRoute, getRequests, deferredResponse } from "../../../test/network";
import { useEnterAdventure } from "./useEnterAdventure";

const RUN_ID = "01J000000000000000000RUN1";
const ADVENTURE_PATH = `/api/v1/playthrough/campaign/${RUN_ID}/adventure`;

function StartTrigger() {
  const { start, isPending, isError } = useEnterAdventure(RUN_ID);
  return (
    <div>
      <button onClick={start} disabled={isPending}>
        start
      </button>
      {isError && <p>network error</p>}
    </div>
  );
}

function PlayProbe() {
  const location = useLocation();
  return <p>play screen: {JSON.stringify(location.state)}</p>;
}

function renderTrigger() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[`/runs/${RUN_ID}`]}>
        <Routes>
          <Route path="/runs/:runId" element={<StartTrigger />} />
          <Route path="/runs/:runId/play" element={<PlayProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("useEnterAdventure (AC5)", () => {
  it("posts to the enter-adventure endpoint and navigates to the play screen with the one-shot flag", async () => {
    mockRoute("POST", ADVENTURE_PATH, { status: 201, body: { id: "adv-1", status: "active" } });
    renderTrigger();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "start" }));

    expect(await screen.findByText('play screen: {"startOpening":true}')).toBeInTheDocument();
    expect(getRequests({ method: "POST", path: ADVENTURE_PATH })).toHaveLength(1);
  });

  it("disables the button while the request is in flight", async () => {
    const deferred = deferredResponse();
    mockRoute("POST", ADVENTURE_PATH, () => deferred.promise);
    renderTrigger();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "start" }));

    expect(screen.getByRole("button", { name: "start" })).toBeDisabled();

    deferred.resolve({ status: 201, body: { id: "adv-1", status: "active" } });
    await screen.findByText('play screen: {"startOpening":true}');
  });

  it("a 409 ADVENTURE_ACTIVE still counts as success and navigates", async () => {
    mockRoute("POST", ADVENTURE_PATH, {
      status: 409,
      body: { error: { code: "ADVENTURE_ACTIVE", message: "already active", details: null } },
    });
    renderTrigger();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "start" }));

    expect(await screen.findByText('play screen: {"startOpening":true}')).toBeInTheDocument();
  });

  it("a 500 shows the network error line and the button stays pressable", async () => {
    mockRoute("POST", ADVENTURE_PATH, {
      status: 500,
      body: { error: { code: "INTERNAL_ERROR", message: "boom", details: null } },
    });
    renderTrigger();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "start" }));

    expect(await screen.findByText("network error")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "start" })).not.toBeDisabled());
  });
});
