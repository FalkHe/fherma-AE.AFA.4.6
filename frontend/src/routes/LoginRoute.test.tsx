import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, stubFetch } from "../test/network";
import { renderWithProviders } from "../test/render";

import { LoginRoute } from "./LoginRoute";

/**
 * This file deliberately opts out of two conveniences of the test environment,
 * because both of them hide the class of bug it exists to catch.
 *
 * The screen disables every input while the sign-in request is in flight, and a
 * mutation's `onError` callback runs *before* React commits the error render —
 * so a programmatic `focus()` issued from that callback lands on an input that
 * is still disabled, which a browser silently ignores. Neither half of that is
 * observable under the defaults:
 *
 * - `act()` flushes updates synchronously, so the pending render is already
 *   replaced by the time the callback runs → `IS_REACT_ACT_ENVIRONMENT = false`
 *   makes React render concurrently, the way the browser does.
 * - a stub that answers in a microtask never lets the pending render commit at
 *   all → the response is delayed instead.
 * - jsdom's `focus()` ignores the `disabled` attribute → patched below to
 *   refuse, as every real browser does.
 *
 * Without all three, this test passes against the broken implementation.
 */

const actEnvironment = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };
let previousActEnvironment: boolean | undefined;

beforeAll(() => {
  previousActEnvironment = actEnvironment.IS_REACT_ACT_ENVIRONMENT;
  actEnvironment.IS_REACT_ACT_ENVIRONMENT = false;
});

afterAll(() => {
  // Restored so this file cannot change how any other one renders.
  actEnvironment.IS_REACT_ACT_ENVIRONMENT = previousActEnvironment;
});

/** Makes `focus()` a no-op on a disabled element, as browsers do. */
function enforceBrowserFocusRules() {
  const nativeFocus = HTMLElement.prototype.focus;

  // `restoreMocks` in vitest.config.ts puts the original back after each test.
  vi.spyOn(HTMLElement.prototype, "focus").mockImplementation(function (
    this: HTMLElement,
    options?: FocusOptions,
  ) {
    if (this.hasAttribute("disabled")) {
      return;
    }

    nativeFocus.call(this, options);
  });
}

describe("LoginRoute", () => {
  beforeEach(() => {
    enforceBrowserFocusRules();
  });

  it("returns focus to the username field after a rejected sign-in", async () => {
    stubFetch(async (request) => {
      if (new URL(request.url).pathname === "/auth/me") {
        return jsonResponse({ detail: "Not authenticated." }, { status: 401 });
      }

      // Long enough for the pending render — disabled inputs, focus dropped to
      // <body> as the focused submit button is disabled — to actually commit.
      await new Promise((resolve) => setTimeout(resolve, 50));

      return jsonResponse({ detail: "Invalid username or password." }, { status: 401 });
    });
    const user = userEvent.setup();

    renderWithProviders(<LoginRoute />);

    await user.type(await screen.findByLabelText(/Username/), "somebody");
    await user.type(screen.getByLabelText(/Password/), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid username or password.",
    );
    await waitFor(() => expect(screen.getByLabelText(/Username/)).not.toBeDisabled());
    expect(screen.getByLabelText(/Password/)).toHaveValue("");
    await waitFor(() => expect(screen.getByLabelText(/Username/)).toHaveFocus());
  });
});
