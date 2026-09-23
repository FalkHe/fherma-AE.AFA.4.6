// Sprint 010/07 WI2 ← AC2, AC4. Behaviours: the line renders the one
// `thinking.first` wording, inside a region assistive tech announces
// (`aria-live="polite"`) -- nothing about *when* it mounts, since that is
// `Transcript.tsx`'s call (AC4), not this component's.
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "../../../test/render";
import { ThinkingLine } from "./ThinkingLine";
import play from "../../../core/i18n/locales/en/play.json";

describe("ThinkingLine", () => {
  it("renders the thinking.first wording", () => {
    renderWithProviders(<ThinkingLine />);

    expect(screen.getByText(play.thinking.first)).toBeInTheDocument();
  });

  it("puts the wording inside an aria-live polite region so it is announced", () => {
    renderWithProviders(<ThinkingLine />);

    const region = screen.getByTestId("thinking-line");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveTextContent(play.thinking.first);
  });
});
