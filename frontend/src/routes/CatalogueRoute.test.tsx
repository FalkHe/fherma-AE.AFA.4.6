import type { UseQueryResult } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useLocation } from "react-router";

import type { CatalogueFilters } from "../hooks/useCatalogueFilters";
import type { CatalogueModelPage } from "../hooks/useCatalogueModels";
import { queryKeys } from "../queryKeys";
import { catalogueApi } from "../test/catalogueApi";
import { stubFetch } from "../test/network";
import { renderWithProviders } from "../test/render";

import { CatalogueRoute } from "./CatalogueRoute";

/**
 * The catalogue list against a fake catalogue API (`test/catalogueApi.ts`).
 *
 * What is under test is the URL contract: a control writes the search params,
 * the parsed params drive the query key and the request, and a mount at a given
 * URL reproduces both the controls and the results — the "reload/share the view"
 * promise.
 *
 * The list hook is wrapped rather than replaced: the fixture catalogue does the
 * filtering, sorting and paging for the happy paths (through the real request
 * path since step 4.9), and only the states the fixtures cannot produce (an
 * empty catalogue, a failed request) are answered with a canned query result.
 */

/** The filters the route last passed to the data hook — i.e. its query key. */
let observedFilters: CatalogueFilters | null = null;

/** When set, replaces the list query result (states the fixtures cannot reach). */
let listOverride: UseQueryResult<CatalogueModelPage, Error> | null = null;

vi.mock("../hooks/useCatalogueModels", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../hooks/useCatalogueModels")>();

  return {
    ...actual,
    useCatalogueModels: (filters: CatalogueFilters) => {
      observedFilters = filters;

      const result = actual.useCatalogueModels(filters);

      return listOverride ?? result;
    },
  };
});

function queryResult(
  overrides: Partial<UseQueryResult<CatalogueModelPage, Error>>,
): UseQueryResult<CatalogueModelPage, Error> {
  return {
    data: undefined,
    isError: false,
    isFetching: false,
    isLoading: false,
    refetch: vi.fn(),
    ...overrides,
  } as unknown as UseQueryResult<CatalogueModelPage, Error>;
}

function LocationProbe() {
  const { search } = useLocation();

  return <output data-testid="search">{search}</output>;
}

function renderRoute(url = "/catalogue") {
  return renderWithProviders(
    <>
      <CatalogueRoute />
      <LocationProbe />
    </>,
    { initialEntries: [url] },
  );
}

function searchString(): string {
  return screen.getByTestId("search").textContent ?? "";
}

function grid(): HTMLElement {
  return screen.getByLabelText("Catalogue models");
}

/**
 * The card links, by href rather than by role: resolving roles and accessible
 * names over two dozen cards is slow enough to dominate the run.
 */
function cardLinks(): HTMLElement[] {
  return Array.from(grid().querySelectorAll<HTMLElement>('a[href^="/catalogue/"]'));
}

beforeEach(() => {
  observedFilters = null;
  listOverride = null;
  stubFetch(catalogueApi);
  // jsdom has no layout, so the page-change scroll would log "not implemented".
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
});

describe("CatalogueRoute", () => {
  function cardLink(id: string): HTMLElement {
    const link = grid().querySelector(`a[href="/catalogue/${id}"]`);

    expect(link).not.toBeNull();

    return link as HTMLElement;
  }

  it("renders one page of cards with links, specs and the total count", async () => {
    renderRoute();

    expect(await screen.findByText("29 models")).toBeInTheDocument();
    // Page size is 24: the fixture catalogue is deliberately larger.
    expect(cardLinks()).toHaveLength(24);

    const card = cardLink("01STUBHONDACB500F000000000");

    expect(card).toHaveTextContent("Honda · Naked");
    expect(card).toHaveTextContent("Engine displacement: 471 cc");
    expect(within(card).getByRole("img")).toHaveAttribute("alt", "Honda CB500F");
    // A model without a manufacturer renders no separator and no empty line.
    expect(cardLink("01STUBSINNISTERRAIN0000000")).toHaveTextContent("Scrambler");
    // A model with no image at all keeps the card shape with the fallback box.
    expect(
      within(cardLink("01STUBBMWNINET000000000000")).queryByRole("img"),
    ).toBeNull();
  });

  it("writes a filter change to the URL and into the query key", async () => {
    const user = userEvent.setup();

    renderRoute();
    await screen.findByText("29 models");

    await user.click(screen.getByRole("combobox", { name: "Category" }));
    await user.click(screen.getByRole("option", { name: "Naked" }));

    await waitFor(() => {
      expect(searchString()).toBe("?category=naked");
    });
    expect(observedFilters?.category).toEqual(["naked"]);
    expect(queryKeys.catalogue.list(observedFilters ?? {})).toEqual([
      "catalogue",
      "list",
      observedFilters,
    ]);
    expect(await screen.findByText("11 models")).toBeInTheDocument();
  });

  it("resets the page whenever a filter or the sort changes", async () => {
    const user = userEvent.setup();

    renderRoute("/catalogue?page=2");
    await screen.findByText("29 models");

    await user.click(screen.getByRole("checkbox", { name: "A2-eligible only" }));

    await waitFor(() => {
      expect(searchString()).toBe("?a2=1");
    });
    expect(observedFilters?.page).toBe(1);
  });

  it("reproduces filters, controls and results from the URL alone", async () => {
    renderRoute("/catalogue?category=naked&seatMax=800&a2=1&sort=-name");

    expect(await screen.findByText("3 models")).toBeInTheDocument();

    // The controls read the URL — nothing is stored beside it.
    expect(screen.getByRole("combobox", { name: "Category" })).toHaveTextContent("Naked");
    expect(screen.getByLabelText("Max seat height (mm)")).toHaveValue(800);
    expect(screen.getByRole("checkbox", { name: "A2-eligible only" })).toBeChecked();
    expect(screen.getByRole("combobox", { name: "Sort by" })).toHaveTextContent(
      "Name (Z–A)",
    );

    // …and so do the results, in the requested order.
    const links = cardLinks();

    expect(links).toHaveLength(3);
    expect(links[0]).toHaveTextContent(/^Suzuki SV650/);
    expect(links[2]).toHaveTextContent(/^BMW G 310 R/);
  });

  it("pages through the results with the URL", async () => {
    const user = userEvent.setup();

    renderRoute();
    await screen.findByText("29 models");

    await user.click(screen.getByRole("button", { name: "Go to page 2" }));

    await waitFor(() => {
      expect(searchString()).toBe("?page=2");
    });
    await waitFor(() => {
      expect(cardLinks()).toHaveLength(5);
    });
    expect(window.scrollTo).toHaveBeenCalled();
  });

  it("offers to clear the filters when nothing matches", async () => {
    const user = userEvent.setup();

    renderRoute("/catalogue?ccMin=99999");

    expect(await screen.findByText("No models match these filters")).toBeInTheDocument();
    expect(screen.getByText("0 models")).toBeInTheDocument();

    // Two of them: the panel's and the empty state's — the latter is the offer.
    const clearButtons = screen.getAllByRole("button", { name: "Clear filters" });

    await user.click(clearButtons[clearButtons.length - 1]);

    await waitFor(() => {
      expect(searchString()).toBe("");
    });
    expect(await screen.findByText("29 models")).toBeInTheDocument();
  });

  it("points an empty catalogue at the advisor", async () => {
    listOverride = queryResult({ data: { items: [], totalCount: 0 } });

    renderRoute();

    expect(await screen.findByText("The catalogue is empty")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ask the advisor" })).toHaveAttribute(
      "href",
      "/consultations",
    );
  });

  it("shows skeleton cards while the first page loads", () => {
    listOverride = queryResult({ isLoading: true, isFetching: true });

    renderRoute();

    expect(grid()).toHaveAttribute("aria-busy", "true");
    expect(grid().querySelectorAll(".MuiCard-root")).toHaveLength(8);
    expect(
      screen.getByRole("progressbar", { name: "Updating results" }),
    ).toBeInTheDocument();
  });

  it("offers a retry when the list request fails", async () => {
    const refetch = vi.fn();

    listOverride = queryResult({ isError: true, refetch });

    const user = userEvent.setup();

    renderRoute();

    expect(await screen.findByText("Could not load the catalogue")).toBeInTheDocument();
    // The filter panel stays usable next to the error.
    expect(screen.getByRole("combobox", { name: "Category" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(refetch).toHaveBeenCalled();
  });
});
