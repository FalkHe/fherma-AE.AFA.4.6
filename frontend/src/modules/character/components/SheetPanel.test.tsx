// Sprint 009-06, WI1 — AC3. `SheetPanel` is a presentational component
// taking `collapsed` as a plain prop (research.md Decision 6), so both
// layouts are exercised directly without depending on `useMediaQuery` or the
// suite's `matchMedia` stub (which always reads the wide layout —
// research.md fact "Tests").
//
// Creation-chat viewport fix — the wide frame is now a card, and the
// abilities render as cells; the field list must still be a single `<dl>`.
import { describe, expect, it } from "vitest";
import { screen, within } from "@testing-library/react";

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

const FULL_SHEET: SheetSoFar = {
  ...PARTIAL_SHEET,
  alignment: "Chaotic Good",
  abilities: { strength: 8, dexterity: 16, constitution: 14, intelligence: 12, wisdom: 10, charisma: 13 },
  maxHp: 9,
  armourClass: 15,
};

describe("SheetPanel's card (creation-chat viewport fix)", () => {
  it("renders the ability values inside the card, all in one definition list", () => {
    const { container } = renderWithProviders(<SheetPanel sheet={FULL_SHEET} stepNumber={4} collapsed={false} />);

    const card = screen.getByRole("complementary", { name: "Your sheet so far" });
    const lists = container.querySelectorAll("dl");
    expect(lists).toHaveLength(1);
    expect(card).toContainElement(lists[0]);

    for (const value of ["8", "16", "14", "12", "10", "13", "9", "15"]) {
      expect(lists[0]).toContainElement(within(card).getByText(value));
    }
    expect(within(card).getByText("STR")).toBeInTheDocument();
    expect(within(card).getByText("Step 4 of 7")).toBeInTheDocument();
  });
});
