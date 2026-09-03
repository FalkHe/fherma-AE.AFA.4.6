import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { Route, Routes } from "react-router";

import { catalogueApi } from "../test/catalogueApi";
import { stubFetch } from "../test/network";
import { renderWithProviders } from "../test/render";

import { CatalogueModelRoute } from "./CatalogueModelRoute";

/**
 * The model detail page against a fake catalogue API (`test/catalogueApi.ts`).
 *
 * Nothing is doubled here: the route is mounted at a real URL, the real hook
 * requests it, and the three fixture ids stand for the three situations the page
 * has to survive — a fully-populated model, a partially-extracted one, and an id
 * the catalogue does not publish. The assertions are the ones written against
 * the step-4.8 stub: they describe what is on screen, not how it got there.
 */

/** The fixture ids (`test/catalogueApi.ts`). */
const IDS = {
  full: "01STUBSUZUKIGSR60000000000",
  sparse: "01STUBHONDAREBEL5000000000",
  missing: "01STUBMISSING0000000000000",
} as const;

function renderRoute(motorbikeId: string, children?: ReactNode) {
  return renderWithProviders(
    <Routes>
      <Route
        path="/catalogue/:motorbikeId"
        element={children ?? <CatalogueModelRoute />}
      />
    </Routes>,
    { initialEntries: [`/catalogue/${motorbikeId}`] },
  );
}

function specTable(): HTMLElement {
  return screen.getByRole("table", { name: "Verified specifications" });
}

beforeEach(() => {
  stubFetch(catalogueApi);
});

describe("CatalogueModelRoute", () => {
  it("renders the header, the gallery and the attribution of a full model", async () => {
    const { container } = renderRoute(IDS.full);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Suzuki GSR 600" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Catalogue" })).toHaveAttribute(
      "href",
      "/catalogue",
    );
    expect(screen.getByText("Suzuki")).toBeInTheDocument();
    // Chips: the two trims first (the chip row directly under the `h1`, §3.2),
    // then category and price band through the hoisted enum labels — and no
    // A2 chip, because this bike is not A2-eligible (a null would say nothing
    // either; only a verified `true` earns the badge).
    expect(
      Array.from(container.querySelectorAll(".MuiChip-root"), (chip) => chip.textContent),
    ).toEqual([
      "Comfort",
      "Sport",
      "Naked",
      "Budget (under €5,000)",
      // The used-price block's "Market snapshot" chip (§4.1) — icon ligature
      // text plus label, same as every other `Icon`-led `Chip` in this suite.
      "scheduleMarket snapshot",
    ]);

    const gallery = screen.getByRole("group", { name: "Photos of Suzuki GSR 600" });

    expect(within(gallery).getByAltText("Suzuki GSR 600")).toHaveAttribute(
      "src",
      expect.stringContaining("_detail.webp"),
    );
    // Two approved images, so the thumbnail strip appears.
    expect(within(gallery).getAllByRole("button", { name: /Show photo/ })).toHaveLength(
      2,
    );
    expect(
      screen.getByText("Photo: Wikimedia Commons, CC BY-SA 4.0"),
    ).toBeInTheDocument();
  });

  it("groups every known spec and omits the unknown ones", async () => {
    renderRoute(IDS.full);

    expect(await screen.findByText("Engine & performance")).toBeInTheDocument();

    const table = specTable();

    for (const group of [
      "Engine & performance",
      "Dimensions & ergonomics",
      "Licence & safety",
      "Classification & price",
    ]) {
      expect(within(table).getByText(group)).toBeInTheDocument();
    }
    // Values carry their unit; booleans read as words; the price is currency.
    expect(within(table).getByText("599 cc")).toBeInTheDocument();
    expect(within(table).getByText("72.5 kW")).toBeInTheDocument();
    expect(within(table).getByText("16.5 l")).toBeInTheDocument();
    expect(within(table).getByText("Yes")).toBeInTheDocument();
    expect(within(table).getByText("No")).toBeInTheDocument();
    expect(within(table).getByText("€4,200")).toBeInTheDocument();
  });

  it("renders no row for an unknown field and no header for an unknown group", async () => {
    renderRoute(IDS.sparse);

    expect(await screen.findByText("Engine & performance")).toBeInTheDocument();

    const table = specTable();

    expect(within(table).getByText("471 cc")).toBeInTheDocument();
    expect(within(table).getByText("Mid (€5,000–10,000)")).toBeInTheDocument();
    // Unknown fields: no row, no em dash, no guess.
    expect(within(table).queryByText("Cylinders")).toBeNull();
    expect(within(table).queryByText("Top speed")).toBeNull();
    // …and a group nobody could extract renders no header either.
    expect(within(table).queryByText("Licence & safety")).toBeNull();
  });

  it("renders the trims chip row and the spec-table delta group (ui-spec §3.2)", async () => {
    const { container } = renderRoute(IDS.full);

    await screen.findByRole("heading", { level: 1, name: "Suzuki GSR 600" });

    // Two chips — one description-only, one carrying a delta.
    expect(
      Array.from(container.querySelectorAll(".MuiChip-root"), (chip) => chip.textContent),
    ).toEqual([
      "Comfort",
      "Sport",
      "Naked",
      "Budget (under €5,000)",
      // The used-price block's "Market snapshot" chip (§4.1) — icon ligature
      // text plus label, same as every other `Icon`-led `Chip` in this suite.
      "scheduleMarket snapshot",
    ]);

    // One delta row, appended as a final group titled "Trims", never phrased
    // as a filter promise.
    const table = specTable();

    expect(within(table).getByText("Trims")).toBeInTheDocument();
    expect(
      within(table).getByRole("rowheader", { name: "Sport" }),
    ).toBeInTheDocument();
    expect(
      within(table).getByText("Wet weight: 192 kg · Seat height: 800 mm"),
    ).toBeInTheDocument();
    // The description-only trim never gets a table row of its own.
    expect(within(table).queryByText("Comfort")).toBeNull();
  });

  it("renders no trim chips and no trims group when `variants` is absent (§11 degradation)", async () => {
    const { container } = renderRoute(IDS.sparse);

    await screen.findByText("Engine & performance");

    expect(screen.queryByText("Trims")).toBeNull();
    // Only the category/price-band chips this fixture already carries — no
    // trim chip is mixed in ahead of them.
    expect(
      Array.from(container.querySelectorAll(".MuiChip-root"), (chip) => chip.textContent),
    ).toEqual(["Cruiser", "Mid (€5,000–10,000)"]);
  });

  it("renders the article as GFM and leaves raw HTML inert", async () => {
    const { container } = renderRoute(IDS.full);

    expect(await screen.findByText("About this bike")).toBeInTheDocument();
    // The article's own `##` headings are demoted below the page's sections.
    expect(screen.getByRole("heading", { level: 3, name: "Design" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: "Reception" }),
    ).toBeInTheDocument();

    // GFM: the pipe table becomes a real table (the unlabelled one — the spec
    // table carries an `aria-label`).
    const articleTable = screen
      .getAllByRole("table")
      .find((table) => !table.hasAttribute("aria-label"));

    expect(articleTable).toBeDefined();
    expect(within(articleTable as HTMLElement).getByText("Launched in Europe"))
      .toBeInTheDocument();
    expect(
      within(articleTable as HTMLElement).getByRole("columnheader", { name: "Year" }),
    ).toBeVisible();

    // Raw HTML is off: the script tag arrives as text and never as an element.
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain(
      "<script>window.__catalogueStubPwned = true;</script>",
    );
    expect(
      (window as unknown as Record<string, unknown>).__catalogueStubPwned,
    ).toBeUndefined();
  });

  it("lists the sources once each, as external links or plain text", async () => {
    renderRoute(IDS.full);

    const list = await screen.findByRole("list", { name: "Sources" });
    const links = within(list).getAllByRole("link");

    // The duplicate Wikipedia URL is folded away; the upload is not a link.
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute(
      "href",
      "https://en.wikipedia.org/wiki/Suzuki_GSR600",
    );
    expect(links[0]).toHaveAttribute("target", "_blank");
    expect(links[0]).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(within(list).getByText("en.wikipedia.org")).toBeInTheDocument();
    expect(within(list).getByText("Owner's manual (uploaded)")).toBeInTheDocument();
    expect(within(list).getByText("Uploaded document")).toBeInTheDocument();
  });

  it("falls back to the placeholder and drops the article for a sparse model", async () => {
    renderRoute(IDS.sparse);

    const gallery = await screen.findByRole("group", {
      name: "Photos of Honda Rebel 500",
    });

    // No approved image: the fallback box keeps the page's shape.
    expect(within(gallery).queryByRole("img")).toBeNull();
    expect(within(gallery).getByText("two_wheeler")).toBeInTheDocument();
    // No prose: the block is absent, not empty.
    expect(screen.queryByText("About this bike")).toBeNull();
    // The sources block stays — it is the page's provenance surface.
    expect(screen.getByRole("list", { name: "Sources" })).toBeInTheDocument();
  });

  it("renders the used-price block when the detail carries one (ui-spec §4.2)", async () => {
    renderRoute(IDS.full);

    expect(await screen.findByText("Used market price")).toBeInTheDocument();
    expect(screen.getByText("€3,900 – €5,600")).toBeInTheDocument();
    expect(screen.getByText("Market snapshot")).toBeInTheDocument();
  });

  it("renders no used-price block, no heading, when the member is absent", async () => {
    renderRoute(IDS.sparse);

    await screen.findByText("Engine & performance");

    expect(screen.queryByText("Used market price")).toBeNull();
  });

  it("answers an unpublished or unknown id with the not-found state", async () => {
    // A nested provider, only here: the application retries a failed query three
    // times with backoff (~7 s), and this test is about the state, not the wait.
    renderRoute(
      IDS.missing,
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <CatalogueModelRoute />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Model not found")).toBeInTheDocument();
    expect(
      screen.getByText("This model does not exist or is not published."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Catalogue" })).toHaveAttribute(
      "href",
      "/catalogue",
    );
    expect(screen.queryByRole("table")).toBeNull();
  });
});
