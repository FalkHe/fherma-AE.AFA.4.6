import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../test/render";

import { AppErrorBoundary } from "./AppErrorBoundary";

/**
 * The boundary catches a render crash and offers a full-page reload; a
 * healthy child passes straight through, unwrapped.
 */

function Bomb(): never {
  throw new Error("boom");
}

let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
let reloadSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  // React (and this boundary's own `componentDidCatch`) logs the crash —
  // expected here, so it is silenced rather than left as test noise.
  consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
  reloadSpy = vi.fn();
  vi.stubGlobal("location", { ...window.location, reload: reloadSpy });
});

afterEach(() => {
  consoleErrorSpy.mockRestore();
  vi.unstubAllGlobals();
});

describe("AppErrorBoundary", () => {
  it("renders a healthy child unchanged", () => {
    renderWithProviders(
      <AppErrorBoundary>
        <p>All good</p>
      </AppErrorBoundary>,
    );

    expect(screen.getByText("All good")).toBeInTheDocument();
  });

  it("swaps a render crash for the fallback and reloads on request", async () => {
    renderWithProviders(
      <AppErrorBoundary>
        <Bomb />
      </AppErrorBoundary>,
    );

    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(
      screen.getByText(
        "An unexpected error broke this page. Reloading usually fixes it.",
      ),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Reload page" }));

    expect(reloadSpy).toHaveBeenCalledTimes(1);
  });
});
