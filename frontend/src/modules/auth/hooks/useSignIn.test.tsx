// AC2, AC5: on success, useSignIn navigates to the remembered address
// (`state.from`) or "/" when none was remembered, and does so before
// writing the `currentUser` cache — see RequireAnonymous.test.tsx for the
// guard-side half of the same race. Exercised directly against the hook
// (no route component involved) so these stay unit-level.
import { useEffect, useRef } from "react";
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation, type Location } from "react-router";

import { createQueryClient } from "../../../core/queryClient";
import { mockRoute } from "../../../test/network";
import { useSignIn } from "./useSignIn";
import type { AuthRedirectState } from "../components/RequireAuth";

const USER = { id: "01ARZ3NDEKTSV4RRFFQ69G5FAV", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" };

function stubSignInSuccess() {
  mockRoute("POST", "/api/v1/auth/sign-in", {
    status: 200,
    body: USER,
    headers: { "X-CSRF-Token": "csrf-token-value" },
  });
}

interface RouterProbeApi {
  getLocation: () => Location;
}

function RouterProbe({ onReady }: { onReady: (api: RouterProbeApi) => void }) {
  const location = useLocation();
  const locationRef = useRef(location);

  useEffect(() => {
    locationRef.current = location;
  });

  useEffect(() => {
    onReady({ getLocation: () => locationRef.current });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}

function SignInTrigger() {
  const { mutate } = useSignIn();
  return (
    <button onClick={() => mutate({ username: "thorin", password: "hunter-of-orcs" })}>trigger sign in</button>
  );
}

function renderSignIn(initialState?: AuthRedirectState) {
  let api: RouterProbeApi | undefined;

  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[{ pathname: "/signin", state: initialState }]}>
        <RouterProbe
          onReady={(readyApi) => {
            api = readyApi;
          }}
        />
        <SignInTrigger />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  return { getLocation: () => api!.getLocation() };
}

describe("useSignIn (AC2)", () => {
  it("with no remembered address (direct visit to /signin), lands on /", async () => {
    stubSignInSuccess();
    const app = renderSignIn();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "trigger sign in" }));

    await waitFor(() => expect(app.getLocation().pathname).toBe("/"));
  });

  it("with a remembered protected address, lands on that address including its query string and fragment", async () => {
    stubSignInSuccess();
    const app = renderSignIn({
      from: { pathname: "/dashboard", search: "?tab=quests", hash: "#loot", state: null, key: "deep-link" },
    });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "trigger sign in" }));

    await waitFor(() => expect(app.getLocation().pathname).toBe("/dashboard"));
    expect(app.getLocation().search).toBe("?tab=quests");
    expect(app.getLocation().hash).toBe("#loot");
  });
});
