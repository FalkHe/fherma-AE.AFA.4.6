// Creation-chat viewport fix — while a message is in flight the field turns
// read-only, not disabled, so focus stays in it; only Send is disabled, and
// an Enter meanwhile sends nothing.
import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../../test/render";
import character from "../../../core/i18n/locales/en/character.json";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("keeps the field enabled and focused while sending, and a submit then is a no-op", async () => {
    const onSend = vi.fn();
    const { rerender } = renderWithProviders(<Composer onSend={onSend} disabled={false} />);
    const user = userEvent.setup();

    const field = screen.getByLabelText(character.chat.placeholder);
    await user.type(field, "a halfling rogue");
    expect(field).toHaveFocus();

    rerender(<Composer onSend={onSend} disabled />);

    expect(field).toBeEnabled();
    expect(field).toHaveAttribute("readonly");
    expect(field).toHaveFocus();
    expect(screen.getByRole("button", { name: character.chat.send })).toBeDisabled();

    await user.keyboard("{Enter}");
    // Also bypassing the disabled button: the form's own submit is guarded.
    fireEvent.submit(field.closest("form")!);
    expect(onSend).not.toHaveBeenCalled();
    expect(field).toHaveValue("a halfling rogue");

    rerender(<Composer onSend={onSend} disabled={false} />);
    await user.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledWith("a halfling rogue");
  });
});
