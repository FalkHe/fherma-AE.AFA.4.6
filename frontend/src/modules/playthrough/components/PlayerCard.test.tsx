// Sprint 009-07, WI1, AC4: once a member's `character` is set, the player
// card carries the finished character's facts and drops "Create character"
// — rendered through `PartySection` (not just `PlayerCard` alone) so the
// "n of m characters ready" readout is exercised against the same data,
// exactly as the brief's outcome describes it.
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "../../../test/render";
import { PartySection } from "./PartySection";
import playthrough from "../../../core/i18n/locales/en/playthrough.json";

const CHARACTER = {
  id: "char-1",
  name: "Pip Underbough",
  race: "Halfling",
  characterClass: "Rogue",
  level: 1,
  currentHp: 9,
  maxHp: 9,
  armourClass: 14,
  appearance:
    "Barely three feet of him, all elbows and grin. Curly black hair, a nose broken twice, and boots so quiet the floorboards forget he stood on them.",
};

const READY_MEMBER = { userId: "u1", username: "thorin", role: "owner", ready: true, character: CHARACTER };

describe("PlayerCard's character card (sprint 009-07, WI1, AC4)", () => {
  it("AC4: a member with a character shows its facts, drops 'Create character', and the party line counts it", () => {
    renderWithProviders(<PartySection runId="r1" members={[READY_MEMBER]} />);

    expect(screen.getByText("Pip Underbough")).toBeInTheDocument();
    expect(screen.getByText("Halfling Rogue · Level 1")).toBeInTheDocument();
    expect(screen.getByText("HP 9")).toBeInTheDocument();
    expect(screen.getByText("AC 14")).toBeInTheDocument();
    expect(screen.getByText(CHARACTER.appearance)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: playthrough.party.card.createCharacter })).not.toBeInTheDocument();
    expect(screen.getByText("1 of 1 characters ready")).toBeInTheDocument();
  });
});
