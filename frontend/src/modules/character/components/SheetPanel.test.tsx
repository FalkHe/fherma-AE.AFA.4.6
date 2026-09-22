// Sprint 009-06, WI1 — AC3. `SheetPanel` is a presentational component
// taking `collapsed` as a plain prop (research.md Decision 6), so both
// layouts are exercised directly without depending on `useMediaQuery` or the
// suite's `matchMedia` stub (which always reads the wide layout —
// research.md fact "Tests").
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "../../../test/render";
import type { SheetSoFar } from "../hooks/useCreationChat";
import { SheetPanel } from "./SheetPanel";

const PARTIAL_SHEET: SheetSoFar = {
  name: "Pip Underbough",
  race: "Halfling",
  characterClass: "Rogue",
  level: 1,
  alignment: null,
  abilities: null,
  maxHp: null,
  armourClass: null,
  skills: [],
  equipment: [],
};

describe("SheetPanel (AC3)", () => {
  it("shows set fields, '—' for empty fields and the step reached, expanded and collapsed alike", () => {
    const { unmount } = renderWithProviders(<SheetPanel sheet={PARTIAL_SHEET} stepNumber={2} collapsed={false} />);

    expect(screen.getByText("Pip Underbough")).toBeInTheDocument();
    expect(screen.getByText("Halfling")).toBeInTheDocument();
    expect(screen.getByText("Rogue")).toBeInTheDocument();
    expect(screen.getByText("Alignment")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getByText("Step 2 of 7")).toBeInTheDocument();
    unmount();

    renderWithProviders(<SheetPanel sheet={PARTIAL_SHEET} stepNumber={2} collapsed />);

    expect(screen.getByText("Halfling Rogue · Level 1 · step 2 of 7")).toBeInTheDocument();
    expect(screen.getByText("Pip Underbough")).toBeInTheDocument();
    expect(screen.getByText("Step 2 of 7")).toBeInTheDocument();
  });
});
