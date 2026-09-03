import type { UseQueryResult } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "../../api/schema";
import type { Operation } from "../../hooks/useOperations";
import { ProductError, type Product, type ProductStatus } from "../../hooks/useProducts";
import { jsonResponse, stubFetch, stubPendingFetch } from "../../test/network";
import { renderWithProviders } from "../../test/render";

import { AdminModelReviewRoute } from "./AdminModelReviewRoute";

/**
 * The page-gate matrix of the review screen: which of the five statuses shows
 * tabs, which replaces them with an explanation, and which offers the action
 * bar. `useProduct` is doubled per case because that is the only input the gates
 * read; everything else — the documents/image panels, the status `PATCH` — runs
 * against the in-memory API below.
 */

const PRODUCT_ID = "01PRODUCTINREVIEW000000001";

const UNSAVED_WARNING =
  "You have unsaved spec edits — approval publishes the last saved draft, " +
  "not your current changes.";

const BASE_PRODUCT: Product = {
  id: PRODUCT_ID,
  name: "Suzuki GSR 600",
  slug: "suzuki-gsr-600",
  manufacturer: "Suzuki",
  modelName: "GSR 600",
  yearFrom: 2006,
  yearTo: 2011,
  status: "in_review",
  draftSpec: null,
  verifiedSpec: null,
  createdAt: "2026-08-25T09:03:00Z",
  updatedAt: "2026-08-25T09:14:00Z",
  queryName: "Suzuki GSR 600",
  buildingline: null,
  typeCodes: [],
  variants: [],
  suggestion: null,
};

/** What the doubled `useProduct` answers with; set per test. */
let productQuery: Partial<UseQueryResult<Product, Error>>;

/**
 * When set, replaces the documents/image query result. A real failure would
 * hit the query's default retry budget before settling, so — same idiom as
 * `CatalogueRoute.test.tsx`'s `listOverride` — the hooks are wrapped rather
 * than replaced, and only the states the fixture API cannot reach (pending,
 * failed) are answered with a canned override.
 */
let documentsOverride: Partial<UseQueryResult<unknown, Error>> | null = null;
let imageOverride: Partial<UseQueryResult<unknown, Error>> | null = null;

vi.mock("../../hooks/useProductReview", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../hooks/useProductReview")>();

  return {
    ...actual,
    useProduct: () => ({ refetch: vi.fn(), ...productQuery }),
    useProductDocuments: (productId: string) => {
      const result = actual.useProductDocuments(productId);

      if (documentsOverride === null) {
        return result;
      }

      return {
        ...result,
        ...documentsOverride,
        // Clearing the override before the real refetch settles is what makes
        // a retry land on the real (successful) fixture data.
        refetch: (...args: Parameters<typeof result.refetch>) => {
          documentsOverride = null;
          return result.refetch(...args);
        },
      };
    },
    useProductImage: (productId: string) => {
      const result = actual.useProductImage(productId);

      if (imageOverride === null) {
        return result;
      }

      return {
        ...result,
        ...imageOverride,
        refetch: (...args: Parameters<typeof result.refetch>) => {
          imageOverride = null;
          return result.refetch(...args);
        },
      };
    },
  };
});

function withStatus(status: ProductStatus): void {
  productQuery = {
    data: { ...BASE_PRODUCT, status },
    isLoading: false,
    isError: false,
  };
}

/** The one operation of the model; `null` for "the model never ran". */
let latestOperation: Pick<Operation, "status" | "progress" | "message"> | null = null;

/** Bodies of every `PATCH` the route sent, so the transitions are observable. */
let patches: components["schemas"]["ProductPatchRequest"][];

/**
 * The retrieved Wikipedia article of the reviewed model: headings, a GFM table
 * (which is what proves the react-markdown configuration) and a line of raw HTML
 * that must reach the page as text, never as markup.
 */
const WIKIPEDIA_MARKDOWN = `# Suzuki GSR 600

The **GSR 600** is a naked bike Suzuki built between 2006 and 2011.

| Specification | Value |
| --- | --- |
| Engine | 599 cm³ inline-four |
| Power | 72 kW at 12,000 rpm |

<b>Raw HTML is disabled</b> — this line and <script>alert("xss")</script> are
rendered as text, never as markup.
`;

const DOCUMENT_RESOURCE: components["schemas"]["DocumentResource"] = {
  id: "01DOCWIKIPEDIA000000000001",
  type: "documents",
  attributes: {
    sourceType: "wikipedia",
    sourceUrl: "https://en.wikipedia.org/wiki/Suzuki_GSR600",
    sourceTitle: "Suzuki GSR600",
    contentMarkdown: WIKIPEDIA_MARKDOWN,
    fetchedAt: "2026-08-25T09:04:00Z",
    createdAt: "2026-08-25T09:04:01Z",
  },
};

const IMAGE_RESOURCE: components["schemas"]["ProductImageResource"] = {
  id: "01IMAGEWIKIMEDIA000000001",
  type: "product-images",
  attributes: {
    sourceUrl: "https://upload.wikimedia.org/wikipedia/commons/3/3f/GSR600.jpg",
    attribution: "Jane Doe · CC BY-SA 3.0",
    status: "pending",
    variants: {
      thumb: `/media/motorbikes/${PRODUCT_ID}/01IMAGEWIKIMEDIA000000001_thumb.webp`,
      card: `/media/motorbikes/${PRODUCT_ID}/01IMAGEWIKIMEDIA000000001_card.webp`,
      detail: `/media/motorbikes/${PRODUCT_ID}/01IMAGEWIKIMEDIA000000001_detail.webp`,
    },
    createdAt: "2026-08-25T09:11:00Z",
  },
};

function installApi(): void {
  patches = [];

  stubFetch(async (request) => {
    const url = new URL(request.url);

    if (url.pathname === "/api/documents") {
      return jsonResponse({ data: [DOCUMENT_RESOURCE], meta: { totalCount: 1 } });
    }

    if (url.pathname === "/api/product-images") {
      return jsonResponse({ data: [IMAGE_RESOURCE], meta: { totalCount: 1 } });
    }

    if (url.pathname === "/api/manufacturers") {
      return jsonResponse({
        data: [
          { id: "01MANUFACTURERSUZUKI0001", type: "manufacturers", attributes: { name: "Suzuki" } },
        ],
        meta: { totalCount: 1 },
      });
    }

    if (url.pathname === "/api/manufacturers/01MANUFACTURERSUZUKI0001/buildinglines") {
      return jsonResponse({ data: [] });
    }

    if (url.pathname === "/api/operations") {
      const rows =
        latestOperation === null
          ? []
          : [
              {
                id: "01OPERATIONINGESTION0001",
                type: "operations" as const,
                attributes: {
                  type: "ingestion",
                  error: null,
                  entityType: "motorbike",
                  entityId: PRODUCT_ID,
                  createdAt: "2026-08-25T09:03:00Z",
                  startedAt: "2026-08-25T09:03:04Z",
                  finishedAt: null,
                  ...latestOperation,
                },
              },
            ];

      return jsonResponse({ data: rows, meta: { totalCount: rows.length } });
    }

    if (request.method === "PATCH") {
      patches.push(
        (await request.json()) as components["schemas"]["ProductPatchRequest"],
      );

      return jsonResponse({
        data: { id: PRODUCT_ID, type: "products", attributes: BASE_PRODUCT },
      });
    }

    throw new Error(`Unexpected ${request.method} ${request.url}`);
  });
}

beforeEach(() => {
  latestOperation = null;
  documentsOverride = null;
  imageOverride = null;
  withStatus("in_review");
  installApi();
});

describe("AdminModelReviewRoute gates", () => {
  it("shows the guard spinner while the product is loading", () => {
    productQuery = { isLoading: true, isError: false };
    renderWithProviders(<AdminModelReviewRoute />);

    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
  });

  it("distinguishes a missing model from a failed request", () => {
    productQuery = { isLoading: false, isError: true, error: new ProductError(404) };
    const { unmount } = renderWithProviders(<AdminModelReviewRoute />);

    expect(screen.getByText("Model not found")).toBeInTheDocument();
    unmount();

    productQuery = { isLoading: false, isError: true, error: new ProductError(500) };
    renderWithProviders(<AdminModelReviewRoute />);

    expect(screen.getByText("Could not load this model")).toBeInTheDocument();
  });

  it("replaces the tabs with live progress while the model is ingesting", async () => {
    withStatus("ingesting");
    latestOperation = {
      status: "running",
      progress: 40,
      message: "Fetching sources (2/6)",
    };
    renderWithProviders(<AdminModelReviewRoute />);

    expect(screen.getByText("Ingestion in progress")).toBeInTheDocument();
    expect(
      await screen.findByRole("progressbar", {
        name: "Ingestion progress for Suzuki GSR 600",
      }),
    ).toHaveAttribute("aria-valuenow", "40");
    expect(screen.queryByRole("tab", { name: "Documents" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve & publish" }),
    ).not.toBeInTheDocument();
  });

  it("offers to start ingestion for a model that has not run yet", async () => {
    withStatus("backlog");
    renderWithProviders(<AdminModelReviewRoute />);

    expect(screen.getByText("This model has not been ingested yet.")).toBeInTheDocument();
    // Leftovers from an earlier run stay reviewable, so the tabs remain.
    expect(screen.getByRole("tab", { name: "Documents" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Start ingestion" }));
    await waitFor(() => {
      expect(patches).toHaveLength(1);
    });
    expect(patches[0].data.attributes.status).toBe("ingesting");
  });

  it("offers a retry and the failure line when a rejected run failed", async () => {
    withStatus("rejected");
    latestOperation = {
      status: "failed",
      progress: 15,
      message: "No usable sources could be retrieved",
    };
    renderWithProviders(<AdminModelReviewRoute />);

    expect(
      await screen.findByRole("button", { name: "Retry ingestion" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Ingestion failed — No usable sources could be retrieved"),
    ).toBeInTheDocument();
  });

  it("reviews an in_review model with both actions and the documents tab", async () => {
    renderWithProviders(<AdminModelReviewRoute />);

    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve & publish" })).toBeInTheDocument();
    // The Wikipedia document is selected by default, GFM table included.
    expect(
      await screen.findByRole("heading", { name: "Suzuki GSR600", level: 3 }),
    ).toBeInTheDocument();
    const table = screen.getByRole("table");

    expect(table).toBeInTheDocument();
    // Wide Wikipedia-sourced tables must not push the whole page sideways
    // (ui-spec §10) — the table sits inside its own horizontal scroller,
    // mirroring CatalogueModelRoute's `ProseTable` wrapper.
    expect(table.parentElement).toHaveStyle({ overflowX: "auto" });
    // Raw HTML in retrieved prose renders as text, never as markup.
    const inertHtml = screen.getByText(/rendered as text, never as markup/);

    expect(inertHtml.textContent).toContain('<script>alert("xss")</script>');
    expect(inertHtml.querySelector("script, b")).toBeNull();
  });

  it("shows the documents tab's own loading spinner, not a blank tab", () => {
    documentsOverride = { data: undefined, isLoading: true, isError: false };
    renderWithProviders(<AdminModelReviewRoute />);

    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(screen.queryByText("No documents")).not.toBeInTheDocument();
  });

  it("shows the documents tab's own error state with a working retry", async () => {
    documentsOverride = { data: undefined, isLoading: false, isError: true };
    renderWithProviders(<AdminModelReviewRoute />);

    expect(screen.getByText("Could not load the documents")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(
      await screen.findByRole("heading", { name: "Suzuki GSR600", level: 3 }),
    ).toBeInTheDocument();
  });

  it("shows the image tab's own loading spinner, not a blank tab", async () => {
    imageOverride = { data: undefined, isLoading: true, isError: false };
    renderWithProviders(<AdminModelReviewRoute />);

    await userEvent.click(screen.getByRole("tab", { name: "Image" }));

    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(screen.queryByText("No image")).not.toBeInTheDocument();
  });

  it("shows the image tab's own error state with a working retry", async () => {
    imageOverride = { data: undefined, isLoading: false, isError: true };
    renderWithProviders(<AdminModelReviewRoute />);

    await userEvent.click(screen.getByRole("tab", { name: "Image" }));

    expect(await screen.findByText("Could not load the image")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Attribution / licence")).toBeInTheDocument();
  });

  it("renders a published model read-only", async () => {
    withStatus("approved");
    renderWithProviders(<AdminModelReviewRoute />);

    expect(
      screen.getByText("This model is published. Specs shown are the verified values."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve & publish" }),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Specs" }));

    expect(screen.getByText("Verified specification")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Image" }));

    expect(await screen.findByText("Attribution / licence")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Reject image" }),
    ).not.toBeInTheDocument();
  });
});

describe("AdminModelReviewRoute approval", () => {
  it("warns about unsaved spec edits and publishes on confirmation", async () => {
    renderWithProviders(<AdminModelReviewRoute />);

    await userEvent.click(screen.getByRole("tab", { name: "Specs" }));
    await userEvent.click(screen.getByRole("button", { name: "Approve & publish" }));

    // Nothing edited yet, so the dialog carries no warning.
    expect(screen.getByText("Publish this model?")).toBeInTheDocument();
    expect(screen.queryByText(UNSAVED_WARNING)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.type(screen.getByLabelText("Torque"), "63");
    await userEvent.click(screen.getByRole("button", { name: "Approve & publish" }));

    expect(screen.getByText(UNSAVED_WARNING)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Publish" }));

    await waitFor(() => {
      expect(patches).toHaveLength(1);
    });
    expect(patches[0].data.attributes.status).toBe("approved");
    // The dialog closes on success — the page stays on the model.
    await waitFor(() => {
      expect(screen.queryByText("Publish this model?")).not.toBeInTheDocument();
    });
  });

  it("keeps the reject dialog open and complains when the transition fails", async () => {
    renderWithProviders(<AdminModelReviewRoute />);

    await userEvent.click(screen.getByRole("button", { name: "Reject" }));

    stubFetch(() =>
      jsonResponse(
        { errors: [{ status: "422", code: "invalid-transition", detail: "no" }] },
        { status: 422 },
      ),
    );

    const dialog = within(screen.getByRole("dialog"));

    await userEvent.click(dialog.getByRole("button", { name: "Reject" }));

    expect(
      await screen.findByText("The action failed. Please try again."),
    ).toBeInTheDocument();
    expect(screen.getByText("Reject this model?")).toBeInTheDocument();
  });

  it("disables the dialog while the transition is in flight", async () => {
    renderWithProviders(<AdminModelReviewRoute />);

    await userEvent.click(screen.getByRole("button", { name: "Approve & publish" }));

    stubPendingFetch();
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Publish" })).toBeDisabled();
    });
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });

  it("shows the identity-specific message when approval is blocked (422 incomplete-identity)", async () => {
    renderWithProviders(<AdminModelReviewRoute />);

    await userEvent.click(screen.getByRole("button", { name: "Approve & publish" }));

    stubFetch(() =>
      jsonResponse(
        { errors: [{ status: "422", code: "incomplete-identity", detail: "no" }] },
        { status: 422 },
      ),
    );

    await userEvent.click(screen.getByRole("button", { name: "Publish" }));

    expect(
      await screen.findByText(
        "This model cannot be published yet: manufacturer, model name and start " +
          "year must be filled in the Identity tab first.",
      ),
    ).toBeInTheDocument();
    // The generic failure text is not shown alongside the specific one.
    expect(screen.queryByText("The action failed. Please try again.")).not.toBeInTheDocument();
  });

  it("warns about unsaved identity edits (OR'd with the specs panel's flag)", async () => {
    renderWithProviders(<AdminModelReviewRoute />);

    await userEvent.click(screen.getByRole("tab", { name: "Identity" }));
    await userEvent.type(await screen.findByLabelText("Model name"), "GSR 600");

    await userEvent.click(screen.getByRole("button", { name: "Approve & publish" }));

    expect(screen.getByText(UNSAVED_WARNING)).toBeInTheDocument();
  });
});
