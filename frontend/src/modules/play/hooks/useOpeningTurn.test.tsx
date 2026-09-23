// Sprint 010/08 WI2, I3 ← AC4. The one-shot opening-turn trigger: fires
// `onStart` exactly once when `useLocation().state?.startOpening` is set,
// clears that flag from history so a reload never fires it again, and stays
// silent without the flag or on a plain re-render.
import { StrictMode, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { renderHook, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";

import { useOpeningTurn } from "./useOpeningTurn";

function LocationStateProbe() {
  const location = useLocation();
  return <div data-testid="location-state">{JSON.stringify(location.state)}</div>;
}

function makeWrapper(initialEntries: React.ComponentProps<typeof MemoryRouter>["initialEntries"]) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={initialEntries}>
        {children}
        <LocationStateProbe />
      </MemoryRouter>
    );
  };
}

describe("useOpeningTurn", () => {
  it("fires onStart once and clears the flag when startOpening is set ← AC4", () => {
    const onStart = vi.fn();
    const wrapper = makeWrapper([{ pathname: "/runs/r1/play", state: { startOpening: true } }]);

    const { rerender } = renderHook(() => useOpeningTurn(onStart), { wrapper });

    expect(onStart).toHaveBeenCalledTimes(1);
    // The flag is cleared from history the moment it fires -- a reload
    // (which resurrects the same history entry) must never see it again.
    expect(screen.getByTestId("location-state").textContent).toBe("null");

    rerender();
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it("does not fire without the flag", () => {
    const onStart = vi.fn();
    const wrapper = makeWrapper(["/runs/r1/play"]);

    renderHook(() => useOpeningTurn(onStart), { wrapper });

    expect(onStart).not.toHaveBeenCalled();
    // `MemoryRouter`'s default entry state, absent the flag.
    expect(screen.getByTestId("location-state").textContent).toBe("null");
  });

  it("fires onStart once even under React strict mode's double-invoked effects", () => {
    const onStart = vi.fn();
    const baseWrapper = makeWrapper([{ pathname: "/runs/r1/play", state: { startOpening: true } }]);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <StrictMode>{baseWrapper({ children })}</StrictMode>
    );

    renderHook(() => useOpeningTurn(onStart), { wrapper });

    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it("keeps the latest onStart without retriggering on a re-render alone", () => {
    const firstOnStart = vi.fn();
    const secondOnStart = vi.fn();
    const wrapper = makeWrapper([{ pathname: "/runs/r1/play", state: { startOpening: true } }]);

    const { rerender } = renderHook(({ onStart }) => useOpeningTurn(onStart), {
      wrapper,
      initialProps: { onStart: firstOnStart },
    });
    expect(firstOnStart).toHaveBeenCalledTimes(1);

    rerender({ onStart: secondOnStart });
    expect(secondOnStart).not.toHaveBeenCalled();
  });
});
