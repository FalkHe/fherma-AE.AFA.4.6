import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { kitchenSinkRecommendations } from "../test/chatFixtures";
import { renderWithProviders } from "../test/render";

import { RecommendationCard } from "./RecommendationCard";

/**
 * The payoff card: a self-contained snapshot, non-interactive until the
 * catalogue detail page exists (Phase 4).
 */

const [withImage, withoutImage] = kitchenSinkRecommendations;

/**
 * The test environment sets `VITE_API_URL` (jsdom's `Request` refuses relative
 * URLs), which is exactly the development setup the media prefix exists for.
 */
const mediaBase: string = import.meta.env.VITE_API_URL ?? "";
const cardUrl = `${mediaBase}/media/motorbikes/01BIKECB500F00000000000001/01IMAGE00000000000000001_card.webp`;
const thumbUrl = `${mediaBase}/media/motorbikes/01BIKECB500F00000000000001/01IMAGE00000000000000001_thumb.webp`;

describe("RecommendationCard", () => {
  it("shows the model, its verified key specs and the rationale", () => {
    renderWithProviders(<RecommendationCard recommendation={withImage} />);

    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Honda CB500F");
    expect(screen.getByText("Category: naked")).toBeInTheDocument();
    expect(screen.getByText("Power: 35 kW")).toBeInTheDocument();
    expect(screen.getByText("Wet weight: 189 kg")).toBeInTheDocument();
    expect(screen.getByText("Seat height: 785 mm")).toBeInTheDocument();
    expect(
      screen.getByText("A2-legal, light and the lowest seat of the three."),
    ).toBeInTheDocument();
  });

  it("serves the card image, absolute, and derives the thumb from it", () => {
    renderWithProviders(<RecommendationCard recommendation={withImage} />);

    const image = screen.getByRole("img", { name: "Honda CB500F" });

    // Both variants are prefixed for the cross-origin development setup, and
    // the thumb is the card path with its variant suffix swapped.
    expect(image).toHaveAttribute("src", cardUrl);
    expect(image).toHaveAttribute("srcset", `${thumbUrl} 320w, ${cardUrl} 640w`);
    expect(image).toHaveAttribute("loading", "lazy");
  });

  it("falls back to a placeholder when the model has no approved image", () => {
    renderWithProviders(<RecommendationCard recommendation={withoutImage} />);

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("two_wheeler")).toBeInTheDocument();
  });

  it("omits a key spec that was never verified", () => {
    renderWithProviders(<RecommendationCard recommendation={withoutImage} />);

    expect(screen.getByText("Power: 54 kW")).toBeInTheDocument();
    expect(screen.queryByText(/Seat height/)).not.toBeInTheDocument();
  });

  it("links its whole surface to the model's catalogue page", () => {
    renderWithProviders(<RecommendationCard recommendation={withImage} />);

    // A real href, so middle-click and copy-link work (Phase-4 ui-spec §6).
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      `/catalogue/${withImage.motorbikeId}`,
    );
  });
});
