// Sprint 010/06 WI3 ← AC5 (D12 §2 "Jump to the latest").
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../../test/render";
import { JumpToLatestPill } from "./JumpToLatestPill";
import play from "../../../core/i18n/locales/en/play.json";

describe("JumpToLatestPill", () => {
  it("renders its label from the play:jumpToLatest key and calls its handler when pressed", async () => {
    const onClick = vi.fn();
    renderWithProviders(<JumpToLatestPill onClick={onClick} />);

    const button = screen.getByRole("button", { name: play.jumpToLatest });
    expect(button).toBeInTheDocument();

    await userEvent.click(button);

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
