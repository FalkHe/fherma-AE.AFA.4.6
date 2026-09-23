// Sprint 010/09 WI3 ← AC1, AC3.
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../../test/render";
import { PendingPrompt } from "./PendingPrompt";
import play from "../../../core/i18n/locales/en/play.json";

describe("PendingPrompt", () => {
  it("AC1: renders one button per option, verbatim, and nothing else sends", () => {
    const prompt = { kind: "choice", id: "p1", options: ["Open the door", "Search the room"] } as const;
    renderWithProviders(<PendingPrompt prompt={prompt} onChoose={vi.fn()} onRoll={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Open the door" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Search the room" })).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("AC1: clicking an option button calls onChoose with that option's text", async () => {
    const prompt = { kind: "choice", id: "p1", options: ["Open the door", "Search the room"] } as const;
    const onChoose = vi.fn();
    renderWithProviders(<PendingPrompt prompt={prompt} onChoose={onChoose} onRoll={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Search the room" }));

    expect(onChoose).toHaveBeenCalledTimes(1);
    expect(onChoose).toHaveBeenCalledWith("Search the room");
  });

  it("AC3: renders exactly one roll button naming the notation", () => {
    const prompt = { kind: "roll", id: "p2", notation: "1d20+3" } as const;
    renderWithProviders(<PendingPrompt prompt={prompt} onChoose={vi.fn()} onRoll={vi.fn()} />);

    const expectedLabel = play.roll.button.replace("{{notation}}", "1d20+3");
    expect(screen.getByRole("button", { name: expectedLabel })).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("AC3: clicking the roll button calls onRoll", async () => {
    const prompt = { kind: "roll", id: "p2", notation: "1d20+3" } as const;
    const onRoll = vi.fn();
    renderWithProviders(<PendingPrompt prompt={prompt} onChoose={vi.fn()} onRoll={onRoll} />);

    await userEvent.click(screen.getByRole("button", { name: /1d20\+3/ }));

    expect(onRoll).toHaveBeenCalledTimes(1);
  });
});
