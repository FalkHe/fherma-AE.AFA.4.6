// Sprint 010/07 WI1 ← AC1 (I1).
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../../test/render";
import { Composer } from "./Composer";
import play from "../../../core/i18n/locales/en/play.json";

describe("Composer", () => {
  it("sends trimmed text and clears the field when Send is pressed", async () => {
    const onSend = vi.fn();
    renderWithProviders(<Composer state="open" onSend={onSend} />);

    const field = screen.getByLabelText(play.composer.placeholder);
    await userEvent.type(field, "  open the door  ");
    await userEvent.click(screen.getByRole("button", { name: play.composer.send }));

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith("open the door");
    expect(field).toHaveValue("");
  });

  it("sends trimmed text on Enter", async () => {
    const onSend = vi.fn();
    renderWithProviders(<Composer state="open" onSend={onSend} />);

    const field = screen.getByLabelText(play.composer.placeholder);
    await userEvent.type(field, "look around{Enter}");

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith("look around");
    expect(field).toHaveValue("");
  });

  it("ignores empty or whitespace-only text", async () => {
    const onSend = vi.fn();
    renderWithProviders(<Composer state="open" onSend={onSend} />);

    const field = screen.getByLabelText(play.composer.placeholder);
    await userEvent.type(field, "   {Enter}");

    expect(onSend).not.toHaveBeenCalled();
  });

  it.each([
    ["turnRunning", play.composer.turnRunning],
    ["awaitingChoice", play.composer.awaitingChoice],
    ["awaitingRoll", play.composer.awaitingRoll],
  ] as const)("shows the %s line with nothing clickable", (state, line) => {
    renderWithProviders(<Composer state={state} onSend={vi.fn()} />);

    expect(screen.getByText(line)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
