import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../test/render";

import { ThemeModeToggle } from "./ThemeModeToggle";

describe("ThemeModeToggle", () => {
  it("offers all three modes and applies the one picked", async () => {
    const user = userEvent.setup();

    renderWithProviders(<ThemeModeToggle />);

    const button = screen.getByRole("button", { name: "Change colour theme" });
    // The <Icon> glyph name is the button's only visible content, so it is
    // also the assertable proof of the active mode.
    expect(button).toHaveTextContent("contrast");

    await user.click(button);

    expect(screen.getByRole("menuitem", { name: "System" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Light" })).toBeInTheDocument();

    await user.click(screen.getByRole("menuitem", { name: "Dark" }));

    await waitFor(() => {
      expect(button).toHaveTextContent("dark_mode");
    });
  });
});
