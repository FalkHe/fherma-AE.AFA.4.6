import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { catalogueSearchCall } from "../test/chatFixtures";
import { renderWithProviders } from "../test/render";

import { ToolResultCatalogueSearch } from "./ToolResultCatalogueSearch";
import { isCatalogueSearchResult, type CatalogueSearchResult } from "./toolResults";

/**
 * What the advisor found: only verified values, and a bounded list — the block
 * supports the answer, it does not replace the catalogue.
 */

/** The pinned fixture, narrowed through the same shape check the dispatcher uses. */
function fixtureResult(): CatalogueSearchResult {
  const result = catalogueSearchCall.result;

  if (!isCatalogueSearchResult(result)) {
    throw new Error("the pinned catalogue_search fixture no longer matches its schema");
  }

  return result;
}

function hits(count: number): CatalogueSearchResult {
  return {
    results: Array.from({ length: count }, (_unused, index) => ({
      motorbikeId: `01BIKE${index}`,
      name: `Model ${index}`,
      category: "naked",
      powerKw: 35,
      wetWeightKg: 190,
    })),
  };
}

describe("ToolResultCatalogueSearch", () => {
  it("lists each hit with its verified specs and omits the unverified ones", () => {
    renderWithProviders(<ToolResultCatalogueSearch result={fixtureResult()} />);

    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByText("naked · 35 kW · 189 kg")).toBeInTheDocument();

    // The model without verified specs shows its name and nothing invented.
    const bare = screen.getByText("Moto Morini Seiemmezzo").closest("li");

    expect(bare).not.toBeNull();
    expect(within(bare as HTMLElement).queryByText(/kW/)).not.toBeInTheDocument();
  });

  it("displays eight hits and counts the rest", () => {
    renderWithProviders(<ToolResultCatalogueSearch result={hits(11)} />);

    expect(screen.getAllByRole("listitem")).toHaveLength(8);
    expect(screen.getByText("+ 3 more")).toBeInTheDocument();
  });

  it("shows no counter when everything fits", () => {
    renderWithProviders(<ToolResultCatalogueSearch result={hits(8)} />);

    expect(screen.getAllByRole("listitem")).toHaveLength(8);
    expect(screen.queryByText(/more/)).not.toBeInTheDocument();
  });

  it("says so when the catalogue has no match", () => {
    renderWithProviders(<ToolResultCatalogueSearch result={{ results: [] }} />);

    expect(screen.getByText("No matching models.")).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });
});
