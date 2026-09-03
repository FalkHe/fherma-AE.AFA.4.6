import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import type { components, paths } from "../api/schema";
import { queryKeys } from "../queryKeys";

import { catalogueError } from "./useCatalogueModel";
import type { CatalogueFilters, CatalogueSort } from "./useCatalogueFilters";

/**
 * The customer catalogue's read side: one page of approved models for the
 * current URL state, plus the manufacturer options its filter select offers.
 *
 * Every request goes through the generated `openapi-fetch` client, so the
 * JSON:API envelopes (`data`/`attributes`/`meta`) are typed from the backend's
 * own schema. The envelope is unwrapped here and nowhere else — components see
 * flat rows.
 *
 * This file owns the **only** translation between the SPA's short, shareable
 * search params (ui-spec §3.2) and the wire's `filter[…]` vocabulary: `ccMin` is
 * `filter[engineCcMin]`, `sort=price` is `sort=msrpEur`, and so on. Renderers
 * never see a wire name, and the URL never leaks a backend spelling.
 *
 * Nothing here is cached across filter changes by hand: each distinct parsed
 * filter object is its own query key, and `keepPreviousData` is what keeps the
 * previous grid on screen while the next one loads.
 */

// --- Types ------------------------------------------------------------------

type SummaryAttributes = components["schemas"]["CatalogueModelSummaryAttributes"];

/**
 * Pinned page size, mirrored by the backend request (`page[size]=24`). It lives
 * with the hook that sends it, and the list route imports it to derive the page
 * count from `totalCount`.
 */
export const PAGE_SIZE = 24;

/**
 * One card of the grid (ui-spec §3.5 data needs), typed from the wire's own
 * summary attributes so a backend rename is a type error rather than a blank
 * card.
 *
 * Two deliberate differences to the payload: the resource id is flattened in as
 * `motorbikeId`, and the single `imageUrl` (the *card* variant) becomes both
 * variants a `srcSet` needs — that derivation happens here so
 * `CatalogueModelCard` never does URL arithmetic. Attributes the card does not
 * render (`msrpEur`, `a2Eligible`) are deliberately dropped: the server filters
 * and sorts on them.
 */
export type CatalogueListItem = Pick<
  SummaryAttributes,
  | "name"
  | "manufacturer"
  | "category"
  | "priceBand"
  | "engineCc"
  | "powerKw"
  | "wetWeightKg"
  | "seatHeightMm"
> & {
  motorbikeId: string;
  /** Both variant URLs, ready for `srcSet`, or `null` for a model without one. */
  image: { card: string; thumb: string } | null;
};

/** One page of the catalogue plus the total the pagination and count need. */
export interface CatalogueModelPage {
  items: CatalogueListItem[];
  totalCount: number;
}

/** A manufacturer option of the filter select. */
export type Manufacturer = { id: string } & Pick<
  components["schemas"]["ManufacturerAttributes"],
  "name"
>;

// --- SPA params → wire params ----------------------------------------------

/** The generated query vocabulary of `GET /api/catalogue-models`. */
type ListQuery = NonNullable<
  paths["/api/catalogue-models"]["get"]["parameters"]["query"]
>;

/**
 * The one place `price` becomes `msrpEur`. The SPA spelling is a UX contract
 * (short, shareable URLs); the wire spelling is the column the server sorts on.
 */
const WIRE_SORT = {
  name: "name",
  "-name": "-name",
  price: "msrpEur",
  "-price": "-msrpEur",
} as const satisfies Record<CatalogueSort, components["schemas"]["BrowseSort"]>;

/**
 * The parsed URL state as the endpoint wants it.
 *
 * Absent filters are **omitted**, never sent empty: an unstated bound means
 * "unbounded" server-side, while an empty value would be a request the backend
 * has to interpret. Page and size always travel — this list is genuinely
 * paginated in the UI.
 */
function toListQuery(filters: CatalogueFilters): ListQuery {
  return {
    ...(filters.category.length > 0
      ? { "filter[category]": filters.category.join(",") }
      : {}),
    ...(filters.priceBand.length > 0
      ? { "filter[priceBand]": filters.priceBand.join(",") }
      : {}),
    ...(filters.manufacturer === null
      ? {}
      : { "filter[manufacturer]": filters.manufacturer }),
    ...(filters.ccMin === null ? {} : { "filter[engineCcMin]": filters.ccMin }),
    ...(filters.ccMax === null ? {} : { "filter[engineCcMax]": filters.ccMax }),
    ...(filters.kwMin === null ? {} : { "filter[powerKwMin]": filters.kwMin }),
    ...(filters.kwMax === null ? {} : { "filter[powerKwMax]": filters.kwMax }),
    ...(filters.seatMax === null
      ? {}
      : { "filter[seatHeightMmMax]": filters.seatMax }),
    ...(filters.weightMax === null
      ? {}
      : { "filter[wetWeightKgMax]": filters.weightMax }),
    // Only the "on" state is a filter: A2-eligible unchecked means "no opinion",
    // not "everything that is not A2-eligible".
    ...(filters.a2 ? { "filter[a2Eligible]": true } : {}),
    sort: WIRE_SORT[filters.sort],
    "page[number]": filters.page,
    "page[size]": PAGE_SIZE,
  };
}

// --- Requests ---------------------------------------------------------------

/**
 * Server-relative `/media/…` URLs resolve against Vite in development, where the
 * API lives on another origin — same prefix convention as `api/client.ts`.
 */
const mediaBase: string = import.meta.env.VITE_API_URL ?? "";

/**
 * The pinned suffix swap: the summary payload carries the **card** variant only,
 * and the thumbnail is the same path with its variant suffix exchanged
 * (shared-knowledge, `catalogue-models` list table).
 *
 * Deliberately a second implementation of the swap `RecommendationCard` does
 * privately: two surfaces, two payloads, and one shared helper for two call
 * sites would be a module invented before the third one asks for it.
 */
function imageVariants(imageUrl: string | null): CatalogueListItem["image"] {
  if (imageUrl === null || imageUrl === "") {
    return null;
  }

  return {
    card: mediaBase + imageUrl,
    thumb: mediaBase + imageUrl.replace(/_card\.webp$/, "_thumb.webp"),
  };
}

function toListItem(
  resource: components["schemas"]["CatalogueModelSummaryResource"],
): CatalogueListItem {
  const {
    name,
    manufacturer,
    category,
    priceBand,
    engineCc,
    powerKw,
    wetWeightKg,
    seatHeightMm,
    imageUrl,
  } = resource.attributes;

  return {
    motorbikeId: resource.id,
    name,
    manufacturer,
    category,
    priceBand,
    engineCc,
    powerKw,
    wetWeightKg,
    seatHeightMm,
    image: imageVariants(imageUrl),
  };
}

/** `GET /api/catalogue-models` — exactly one page, as the URL asked for it. */
async function listModels(filters: CatalogueFilters): Promise<CatalogueModelPage> {
  const { data, error, response } = await apiClient.GET("/api/catalogue-models", {
    params: { query: toListQuery(filters) },
  });

  if (!response.ok || data === undefined) {
    // An unknown enum member answers 400 `invalid-filter`; a junk numeric bound
    // answers 422. Both are "could not load" on screen — the URL is the input,
    // and the parser upstream already dropped everything it recognised as junk.
    throw catalogueError(response.status, error);
  }

  return {
    items: data.data.map(toListItem),
    totalCount: data.meta.totalCount,
  };
}

/**
 * Rows per manufacturer request — also the server's maximum.
 *
 * **One request, no page walk** (shared-knowledge, pinned): the table holds a
 * handful of rows, and a `meta.totalCount` above this number is a contract
 * question for the phase owner, not a reason to grow a loop here.
 */
const MANUFACTURER_PAGE_SIZE = 100;

/** `GET /api/manufacturers` — the select's options, in the server's name order. */
async function listManufacturers(): Promise<Manufacturer[]> {
  const { data, error, response } = await apiClient.GET("/api/manufacturers", {
    params: { query: { "page[number]": 1, "page[size]": MANUFACTURER_PAGE_SIZE } },
  });

  if (!response.ok || data === undefined) {
    throw catalogueError(response.status, error);
  }

  return data.data.map((resource) => ({
    id: resource.id,
    name: resource.attributes.name,
  }));
}

// --- Hooks ------------------------------------------------------------------

/**
 * One page of the approved catalogue for the current URL state.
 *
 * `keepPreviousData` is what makes filtering feel instant: the previous grid
 * stays on screen while the next page loads, and the route's reserved progress
 * slot reports the refetch. Every distinct filter/sort/page combination is its
 * own cache entry, keyed by the normalized filter object.
 */
export function useCatalogueModels(
  filters: CatalogueFilters,
): UseQueryResult<CatalogueModelPage, Error> {
  return useQuery({
    queryKey: queryKeys.catalogue.list(filters),
    queryFn: () => listModels(filters),
    placeholderData: keepPreviousData,
  });
}

/**
 * The manufacturer options of the filter select. Near-static, so it is cached
 * for five minutes; a failure leaves the select disabled rather than raising an
 * error surface — the other filters keep working.
 */
export function useManufacturers(): UseQueryResult<Manufacturer[], Error> {
  return useQuery({
    queryKey: queryKeys.manufacturers.list(),
    queryFn: listManufacturers,
    staleTime: 5 * 60_000,
  });
}
