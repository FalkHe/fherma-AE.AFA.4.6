import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";

import type { components } from "../api/schema";

/**
 * The catalogue list view **is** its URL (ui-spec §3.2/§3.3).
 *
 * Every filter, the sort and the page live in React Router search params, and
 * this module owns the only translation between those strings and the typed
 * object the screens and the data hook consume. Nothing here is a stub: the
 * parsing survives step 4.9 untouched, which is why it lives apart from the
 * hooks that talk to the API.
 *
 * Two rules make the URL canonical rather than merely persistent:
 *
 * - **Reading never rewrites.** Junk (`ccMin=abc`, `sort=whatever`, an unknown
 *   category) is ignored on read, not corrected in the address bar — a shared
 *   link keeps whatever it carried.
 * - **Writing omits defaults.** Page 1 and sort `name` never appear, so one
 *   view has exactly one URL.
 */

export type SpecCategory = components["schemas"]["SpecCategory"];
export type PriceBand = components["schemas"]["PriceBand"];

/** The pinned category vocabulary, in the backend's declaration order. */
export const SPEC_CATEGORY_VALUES = [
  "naked",
  "sport",
  "sport_touring",
  "touring",
  "adventure",
  "cruiser",
  "classic",
  "scrambler",
  "enduro",
  "supermoto",
  "scooter",
] as const satisfies readonly SpecCategory[];

/** The pinned price-band vocabulary, cheapest first. */
export const PRICE_BAND_VALUES = [
  "budget",
  "mid",
  "upper",
  "premium",
] as const satisfies readonly PriceBand[];

/**
 * Sort options as they appear in the URL. `price` is the SPA spelling; the data
 * hook maps it to the wire's `msrpEur` — renderers never see wire names.
 */
export const CATALOGUE_SORT_VALUES = ["name", "-name", "price", "-price"] as const;

export type CatalogueSort = (typeof CATALOGUE_SORT_VALUES)[number];

export const DEFAULT_CATALOGUE_SORT: CatalogueSort = "name";

/**
 * The normalized view state. Absent params are `null` / `[]` / `false` — a
 * plain object with a fixed key set, so it doubles as the query key argument.
 *
 * `category` and `priceBand` are sorted alphabetically: `?category=sport,naked`
 * and `?category=naked,sport` are the same view and must share one cache entry.
 */
export type CatalogueFilters = {
  category: SpecCategory[];
  priceBand: PriceBand[];
  /** Manufacturer ULID — opaque to the SPA (ui-spec R2). */
  manufacturer: string | null;
  ccMin: number | null;
  ccMax: number | null;
  kwMin: number | null;
  kwMax: number | null;
  seatMax: number | null;
  weightMax: number | null;
  a2: boolean;
  sort: CatalogueSort;
  page: number;
};

/** What `setFilter` accepts: any filter concept plus the sort, never the page. */
export type CatalogueFilterPatch = Partial<Omit<CatalogueFilters, "page">>;

/** The numeric params, each with its URL name (identical, but typed as a pair). */
const NUMBER_PARAMS = [
  "ccMin",
  "ccMax",
  "kwMin",
  "kwMax",
  "seatMax",
  "weightMax",
] as const;

type NumberParam = (typeof NUMBER_PARAMS)[number];

/** Every param this view owns — the exact set `clearFilters` removes (plus sort). */
const FILTER_PARAMS = [
  "category",
  "priceBand",
  "manufacturer",
  ...NUMBER_PARAMS,
  "a2",
] as const;

function parseList<T extends string>(
  raw: string | null,
  vocabulary: readonly T[],
): T[] {
  if (raw === null) {
    return [];
  }

  const known = raw
    .split(",")
    .map((member) => member.trim())
    .filter((member): member is T => (vocabulary as readonly string[]).includes(member));

  // Sorted so the query key is order-independent; duplicates collapse.
  return [...new Set(known)].sort();
}

/** A positive finite number, or `null` for "not stated" — junk is never an error. */
function parseNumber(raw: string | null): number | null {
  if (raw === null || raw.trim() === "") {
    return null;
  }

  const value = Number(raw);

  return Number.isFinite(value) && value > 0 ? value : null;
}

function parseSort(raw: string | null): CatalogueSort {
  return CATALOGUE_SORT_VALUES.find((value) => value === raw) ?? DEFAULT_CATALOGUE_SORT;
}

function parsePage(raw: string | null): number {
  const value = Number(raw);

  return Number.isInteger(value) && value >= 1 ? value : 1;
}

/**
 * Search params → view state. Exported for tests and for anything that has a
 * `URLSearchParams` but no router context.
 */
export function parseCatalogueFilters(params: URLSearchParams): CatalogueFilters {
  const manufacturer = params.get("manufacturer");

  return {
    category: parseList(params.get("category"), SPEC_CATEGORY_VALUES),
    priceBand: parseList(params.get("priceBand"), PRICE_BAND_VALUES),
    manufacturer: manufacturer === null || manufacturer === "" ? null : manufacturer,
    ccMin: parseNumber(params.get("ccMin")),
    ccMax: parseNumber(params.get("ccMax")),
    kwMin: parseNumber(params.get("kwMin")),
    kwMax: parseNumber(params.get("kwMax")),
    seatMax: parseNumber(params.get("seatMax")),
    weightMax: parseNumber(params.get("weightMax")),
    // Only the literal `1` switches it on: `a2=0` is off, not "present".
    a2: params.get("a2") === "1",
    sort: parseSort(params.get("sort")),
    page: parsePage(params.get("page")),
  };
}

/**
 * How many of the eight filter concepts are active. A min/max pair counts once,
 * the sort never counts — it is a preference, not a filter. Drives the mobile
 * badge and the empty-catalogue vs no-match branch.
 */
export function countActiveFilters(filters: CatalogueFilters): number {
  const concepts = [
    filters.category.length > 0,
    filters.priceBand.length > 0,
    filters.manufacturer !== null,
    filters.ccMin !== null || filters.ccMax !== null,
    filters.kwMin !== null || filters.kwMax !== null,
    filters.seatMax !== null,
    filters.weightMax !== null,
    filters.a2,
  ];

  return concepts.filter(Boolean).length;
}

function writeList(params: URLSearchParams, key: string, values: readonly string[]): void {
  if (values.length === 0) {
    params.delete(key);
  } else {
    params.set(key, [...values].sort().join(","));
  }
}

function writeNumber(params: URLSearchParams, key: NumberParam, value: number | null): void {
  if (value === null) {
    params.delete(key);
  } else {
    params.set(key, String(value));
  }
}

function applyPatch(params: URLSearchParams, patch: CatalogueFilterPatch): void {
  if (patch.category !== undefined) {
    writeList(params, "category", patch.category);
  }
  if (patch.priceBand !== undefined) {
    writeList(params, "priceBand", patch.priceBand);
  }
  if (patch.manufacturer !== undefined) {
    if (patch.manufacturer === null || patch.manufacturer === "") {
      params.delete("manufacturer");
    } else {
      params.set("manufacturer", patch.manufacturer);
    }
  }
  for (const key of NUMBER_PARAMS) {
    const value = patch[key];

    if (value !== undefined) {
      writeNumber(params, key, value);
    }
  }
  if (patch.a2 !== undefined) {
    if (patch.a2) {
      params.set("a2", "1");
    } else {
      params.delete("a2");
    }
  }
  if (patch.sort !== undefined) {
    // The default sort is omitted, so one view keeps one canonical URL.
    if (patch.sort === DEFAULT_CATALOGUE_SORT) {
      params.delete("sort");
    } else {
      params.set("sort", patch.sort);
    }
  }
}

export interface CatalogueFiltersApi {
  /** The normalized view state parsed from the current URL. */
  filters: CatalogueFilters;
  /** Merges a patch into the URL and resets to page 1. */
  setFilter: (patch: CatalogueFilterPatch) => void;
  /**
   * Jumps to a page of the current result set — the one write that keeps the
   * filters. Page 1 drops the param.
   */
  setPage: (page: number) => void;
  /** Removes all eight filter concepts and the page; keeps the sort. */
  clearFilters: () => void;
  activeFilterCount: number;
}

/**
 * The catalogue list's single source of view state.
 *
 * Every control on the screen reads `filters` and writes through `setFilter` —
 * no component keeps its own copy, because a second copy is a second truth and
 * the URL is the one that survives a reload.
 *
 * Writes use `{ replace: true }` (pinned Phase-2 convention): filters are view
 * state, so the back button must leave the page instead of unwinding a series
 * of filter clicks.
 */
export function useCatalogueFilters(): CatalogueFiltersApi {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = useMemo(() => parseCatalogueFilters(searchParams), [searchParams]);

  const setFilter = useCallback(
    (patch: CatalogueFilterPatch) => {
      const params = new URLSearchParams(searchParams);

      applyPatch(params, patch);
      // Any filter or sort change invalidates the current page number: page 7
      // of the old result set means nothing in the new one.
      params.delete("page");
      setSearchParams(params, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const setPage = useCallback(
    (page: number) => {
      const params = new URLSearchParams(searchParams);

      if (page <= 1) {
        params.delete("page");
      } else {
        params.set("page", String(page));
      }
      setSearchParams(params, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const clearFilters = useCallback(() => {
    const params = new URLSearchParams(searchParams);

    for (const key of FILTER_PARAMS) {
      params.delete(key);
    }
    params.delete("page");
    setSearchParams(params, { replace: true });
  }, [searchParams, setSearchParams]);

  return {
    filters,
    setFilter,
    setPage,
    clearFilters,
    activeFilterCount: countActiveFilters(filters),
  };
}
