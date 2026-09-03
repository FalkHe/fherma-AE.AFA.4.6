import { describe, expect, it } from "vitest";

import { countActiveFilters, parseCatalogueFilters } from "./useCatalogueFilters";

/**
 * The URL is the catalogue's view state, so the parsing is the contract: what a
 * shared link means, and what the query key is built from. These are pure
 * function tests — the write side is exercised through the route, where the
 * controls that trigger it live.
 */

function parse(search: string) {
  return parseCatalogueFilters(new URLSearchParams(search));
}

describe("parseCatalogueFilters", () => {
  it("defaults every param to absent", () => {
    expect(parse("")).toEqual({
      category: [],
      priceBand: [],
      manufacturer: null,
      ccMin: null,
      ccMax: null,
      kwMin: null,
      kwMax: null,
      seatMax: null,
      weightMax: null,
      a2: false,
      sort: "name",
      page: 1,
    });
  });

  it("reads every filter of the shareable-URL contract", () => {
    const filters = parse(
      "category=sport,naked&priceBand=mid&manufacturer=01ABC&ccMin=500&ccMax=900" +
        "&kwMin=20&kwMax=70.5&seatMax=820&weightMax=200&a2=1&sort=-price&page=3",
    );

    expect(filters).toEqual({
      // Sorted, so `sport,naked` and `naked,sport` share one cache entry.
      category: ["naked", "sport"],
      priceBand: ["mid"],
      manufacturer: "01ABC",
      ccMin: 500,
      ccMax: 900,
      kwMin: 20,
      kwMax: 70.5,
      seatMax: 820,
      weightMax: 200,
      a2: true,
      sort: "-price",
      page: 3,
    });
  });

  it("ignores what it does not understand instead of failing", () => {
    const filters = parse(
      "category=naked,teleporter&priceBand=free&ccMin=abc&kwMax=-5&seatMax=0" +
        "&a2=0&sort=cheapest&page=0",
    );

    expect(filters.category).toEqual(["naked"]);
    // Every member unknown: the whole filter drops.
    expect(filters.priceBand).toEqual([]);
    expect(filters.ccMin).toBeNull();
    expect(filters.kwMax).toBeNull();
    expect(filters.seatMax).toBeNull();
    // Only the literal `1` switches the flag on.
    expect(filters.a2).toBe(false);
    expect(filters.sort).toBe("name");
    expect(filters.page).toBe(1);
  });
});

describe("countActiveFilters", () => {
  it("counts a min/max pair once and never counts the sort or the page", () => {
    expect(countActiveFilters(parse("ccMin=500&ccMax=900&sort=-name&page=4"))).toBe(1);
    expect(countActiveFilters(parse("category=naked&a2=1&seatMax=820"))).toBe(3);
    expect(countActiveFilters(parse(""))).toBe(0);
  });
});
