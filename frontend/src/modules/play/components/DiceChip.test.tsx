// Sprint 010/09 WI3 ← AC4 (D12 §2 verdict mark).
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "../../../test/render";
import { DiceChip } from "./DiceChip";
import play from "../../../core/i18n/locales/en/play.json";

const baseProps = { label: "Stealth", notation: "1d20+3", breakdown: "13 + 3", total: 16 };

describe("DiceChip", () => {
  it("shows a made-it mark with the accessible name from dice.madeIt when verdict is madeIt", () => {
    renderWithProviders(<DiceChip {...baseProps} verdict="madeIt" />);

    expect(screen.getByRole("img", { name: play.dice.madeIt })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: play.dice.missed })).not.toBeInTheDocument();
  });

  it("shows a missed mark with the accessible name from dice.missed when verdict is missed", () => {
    renderWithProviders(<DiceChip {...baseProps} verdict="missed" />);

    expect(screen.getByRole("img", { name: play.dice.missed })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: play.dice.madeIt })).not.toBeInTheDocument();
  });

  it("draws neither mark when no verdict is given", () => {
    renderWithProviders(<DiceChip {...baseProps} />);

    expect(screen.queryByRole("img", { name: play.dice.madeIt })).not.toBeInTheDocument();
    expect(screen.queryByRole("img", { name: play.dice.missed })).not.toBeInTheDocument();
  });
});
