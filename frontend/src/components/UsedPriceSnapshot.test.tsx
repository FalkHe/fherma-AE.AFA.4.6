import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../test/render";

import type { UsedPrice } from "./usedPrice";
import { UsedPriceSnapshot } from "./UsedPriceSnapshot";

/**
 * The shared used-market snapshot component (ui-spec §4.1), against a bare
 * `UsedPrice` payload — the "snapshot, never a fact" framing common to both
 * call sites.
 */

function priceFixture(overrides: Partial<UsedPrice> = {}): UsedPrice {
  return {
    medianEur: 4800,
    minEur: 3900,
    maxEur: 5600,
    sampleCount: 14,
    asOf: "2026-07-01T00:00:00Z",
    stale: false,
    sources: [
      { title: "kleinanzeigen.de", url: "https://www.kleinanzeigen.de/s-anzeige/example" },
      { title: "mobile.de", url: "https://suchen.mobile.de/example" },
    ],
    ...overrides,
  };
}

function euros(amount: number): string {
  return new Intl.NumberFormat("en", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(amount);
}

describe("UsedPriceSnapshot", () => {
  it("formats the range, median and sample count", () => {
    renderWithProviders(<UsedPriceSnapshot usedPrice={priceFixture()} />);

    expect(
      screen.getByText(`${euros(3900)} – ${euros(5600)}`),
    ).toBeInTheDocument();
    expect(screen.getByText(`Median ${euros(4800)}`, { exact: false })).toBeInTheDocument();
    expect(screen.getByText("14 listings observed", { exact: false })).toBeInTheDocument();
  });

  it("states an unknown sample count rather than hiding it", () => {
    renderWithProviders(
      <UsedPriceSnapshot usedPrice={priceFixture({ sampleCount: null })} />,
    );

    expect(screen.getByText("Sample size unknown", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("listings observed", { exact: false })).toBeNull();
  });

  it("adds the stale caption only when the payload's stale flag is true", () => {
    const { rerender } = renderWithProviders(
      <UsedPriceSnapshot usedPrice={priceFixture({ stale: false })} />,
    );

    expect(
      screen.queryByText(
        "This snapshot is older than the market-data window and may no longer reflect current prices.",
      ),
    ).toBeNull();

    rerender(<UsedPriceSnapshot usedPrice={priceFixture({ stale: true })} />);

    expect(
      screen.getByText(
        "This snapshot is older than the market-data window and may no longer reflect current prices.",
      ),
    ).toBeInTheDocument();
    // Every value keeps rendering next to the caption — the stale flag adds,
    // it never suppresses.
    expect(
      screen.getByText(`${euros(3900)} – ${euros(5600)}`),
    ).toBeInTheDocument();
  });

  it("renders every source as an external link, never behind a tooltip", () => {
    renderWithProviders(<UsedPriceSnapshot usedPrice={priceFixture()} />);

    const links = screen.getAllByRole("link");

    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAccessibleName(/kleinanzeigen\.de/);
    expect(links[0]).toHaveAttribute(
      "href",
      "https://www.kleinanzeigen.de/s-anzeige/example",
    );
    expect(links[0]).toHaveAttribute("target", "_blank");
    expect(links[0]).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(links[1]).toHaveAccessibleName(/mobile\.de/);
  });

  it("renders nothing when usedPrice is null", () => {
    const { container } = renderWithProviders(<UsedPriceSnapshot usedPrice={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when sources is empty (malformed guard)", () => {
    const { container } = renderWithProviders(
      <UsedPriceSnapshot usedPrice={priceFixture({ sources: [] })} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing rather than throwing on a malformed payload", () => {
    const malformed = { minEur: 3900, maxEur: 5600 };
    const { container } = renderWithProviders(<UsedPriceSnapshot usedPrice={malformed} />);

    expect(container).toBeEmptyDOMElement();
  });
});
