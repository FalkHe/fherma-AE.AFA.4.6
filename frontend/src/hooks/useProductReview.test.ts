import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { components } from "../api/schema";
import { jsonResponse, stubFetch } from "../test/network";

import {
  SaveDraftSpecError,
  useProduct,
  useProductDocuments,
  useProductImage,
  useRejectImage,
  useSaveDraftSpec,
  type DraftSpec,
} from "./useProductReview";
import { ProductError } from "./useProducts";

/**
 * The review hooks are exercised through the real request path — the generated
 * client against the stubbed `fetch` — because that is where the JSON:API
 * unwrapping, the document ordering, the newest-image rule and, above all, the
 * merge that makes the full-object `draftSpec` `PATCH` safe actually live.
 */

const PRODUCT_ID = "01PRODUCTINREVIEW000000001";

const DRAFT_SPEC: DraftSpec = {
  category: "naked",
  engineCc: 599,
  cylinders: 4,
  powerKw: 72,
  torqueNm: null,
  wetWeightKg: 209,
  seatHeightMm: 785,
  tankCapacityL: 16.5,
  topSpeedKmh: null,
  abs: false,
  a2Eligible: null,
  priceBand: "budget",
  msrpEur: null,
  extra: { frame: "Steel tube" },
  sourceHints: { powerKw: "Wikipedia infobox" },
  extractedAt: "2026-08-25T09:12:00Z",
};

function productResource(
  overrides: Partial<components["schemas"]["ProductAttributes"]> = {},
): components["schemas"]["ProductResource"] {
  return {
    id: PRODUCT_ID,
    type: "products",
    attributes: {
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
      ...overrides,
    },
  };
}

function documentResource(
  id: string,
  overrides: Partial<components["schemas"]["DocumentAttributes"]> = {},
): components["schemas"]["DocumentResource"] {
  return {
    id,
    type: "documents",
    attributes: {
      sourceType: "wikipedia",
      sourceUrl: "https://en.wikipedia.org/wiki/Suzuki_GSR600",
      sourceTitle: "Suzuki GSR600",
      contentMarkdown: "# Suzuki GSR600",
      fetchedAt: "2026-08-25T09:04:00Z",
      createdAt: "2026-08-25T09:04:01Z",
      ...overrides,
    },
  };
}

function imageResource(
  id: string,
  overrides: Partial<components["schemas"]["ProductImageAttributes"]> = {},
): components["schemas"]["ProductImageResource"] {
  return {
    id,
    type: "product-images",
    attributes: {
      sourceUrl: "https://upload.wikimedia.org/wikipedia/commons/3/3f/GSR600.jpg",
      attribution: "Jane Doe · CC BY-SA 3.0",
      status: "pending",
      variants: {
        thumb: `/media/motorbikes/${PRODUCT_ID}/${id}_thumb.webp`,
        card: `/media/motorbikes/${PRODUCT_ID}/${id}_card.webp`,
        detail: `/media/motorbikes/${PRODUCT_ID}/${id}_detail.webp`,
      },
      createdAt: "2026-08-25T09:11:00Z",
      ...overrides,
    },
  };
}

function mountHook<T>(hook: () => T) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateQueries = vi
    .spyOn(queryClient, "invalidateQueries")
    .mockResolvedValue(undefined);

  function Providers({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  }

  return { view: renderHook(hook, { wrapper: Providers }), invalidateQueries };
}

/** The request the stub last saw, so URL, method and body are assertable. */
interface SeenRequest {
  method: string;
  url: string;
  body: unknown;
}

describe("useProduct", () => {
  it("flattens the product resource into a row", async () => {
    const seen: SeenRequest[] = [];

    stubFetch((request) => {
      seen.push({ method: request.method, url: request.url, body: null });

      return jsonResponse({ data: productResource({ draftSpec: DRAFT_SPEC }) });
    });

    const { view } = mountHook(() => useProduct(PRODUCT_ID));

    await waitFor(() => {
      expect(view.result.current.isSuccess).toBe(true);
    });

    expect(seen[0]).toMatchObject({
      method: "GET",
      url: `http://api.test/api/products/${PRODUCT_ID}`,
    });
    // `id` merged with the attributes: no component sees `.attributes`.
    expect(view.result.current.data).toMatchObject({
      id: PRODUCT_ID,
      name: "Suzuki GSR 600",
      status: "in_review",
      draftSpec: DRAFT_SPEC,
    });
  });

  it("reports a missing model as a ProductError with status 404", async () => {
    stubFetch(() =>
      jsonResponse({ errors: [{ status: "404", code: "not-found", detail: "gone" }] }, {
        status: 404,
      }),
    );

    const { view } = mountHook(() => useProduct(PRODUCT_ID));

    await waitFor(() => {
      expect(view.result.current.isError).toBe(true);
    });

    // The route tells "not found" from "could not load" by exactly this status.
    expect(view.result.current.error).toBeInstanceOf(ProductError);
    expect(view.result.current.error).toMatchObject({ status: 404, code: "not-found" });
  });
});

describe("useProductDocuments", () => {
  it("filters by product and keeps the server's order", async () => {
    const urls: string[] = [];

    stubFetch((request) => {
      urls.push(request.url);

      return jsonResponse({
        data: [
          documentResource("01DOCWIKIPEDIA000000000001"),
          documentResource("01DOCMAGAZINE00000000000001", {
            sourceType: "magazine",
            sourceTitle: "Long-term test",
            sourceUrl: "https://example.invalid/reviews/gsr600",
          }),
        ],
        meta: { totalCount: 2 },
      });
    });

    const { view } = mountHook(() => useProductDocuments(PRODUCT_ID));

    await waitFor(() => {
      expect(view.result.current.isSuccess).toBe(true);
    });

    expect(urls[0]).toContain(`filter[product]=${PRODUCT_ID}`);
    // Unpaginated endpoint: no page parameters are sent at all.
    expect(urls[0]).not.toContain("page");
    // Wikipedia first is the API's ordering, and the panel's "no selection = the
    // first document" rule depends on it surviving the hook untouched.
    expect(view.result.current.data?.map((row) => row.sourceType)).toEqual([
      "wikipedia",
      "magazine",
    ]);
    expect(view.result.current.data?.[0]).toMatchObject({
      id: "01DOCWIKIPEDIA000000000001",
      sourceTitle: "Suzuki GSR600",
      contentMarkdown: "# Suzuki GSR600",
    });
  });

  it("reports a rejected filter as a ProductError with its code", async () => {
    stubFetch(() =>
      jsonResponse(
        { errors: [{ status: "400", code: "missing-filter", detail: "required" }] },
        { status: 400 },
      ),
    );

    const { view } = mountHook(() => useProductDocuments(PRODUCT_ID));

    await waitFor(() => {
      expect(view.result.current.isError).toBe(true);
    });

    expect(view.result.current.error).toMatchObject({
      status: 400,
      code: "missing-filter",
    });
  });
});

describe("useProductImage", () => {
  it("reduces the list to the newest row", async () => {
    stubFetch((request) => {
      expect(new URL(request.url).searchParams.get("filter[product]")).toBe(PRODUCT_ID);

      return jsonResponse({
        data: [
          imageResource("01IMAGEOLDRUN0000000000001", {
            createdAt: "2026-08-24T08:00:00Z",
            status: "rejected",
          }),
          imageResource("01IMAGELATESTRUN000000001", {
            createdAt: "2026-08-25T09:11:00Z",
          }),
        ],
        meta: { totalCount: 2 },
      });
    });

    const { view } = mountHook(() => useProductImage(PRODUCT_ID));

    await waitFor(() => {
      expect(view.result.current.isSuccess).toBe(true);
    });

    // Newest by `createdAt`, not by position: a re-run leaves the older row.
    expect(view.result.current.data).toMatchObject({
      id: "01IMAGELATESTRUN000000001",
      status: "pending",
    });
    expect(view.result.current.data?.variants.detail).toContain("_detail.webp");
  });

  it("answers null when the ingestion found no image", async () => {
    stubFetch(() => jsonResponse({ data: [], meta: { totalCount: 0 } }));

    const { view } = mountHook(() => useProductImage(PRODUCT_ID));

    await waitFor(() => {
      expect(view.result.current.isSuccess).toBe(true);
    });

    // A normal answer, not an error: a model may be published without an image.
    expect(view.result.current.data).toBeNull();
  });
});

describe("useSaveDraftSpec", () => {
  it("merges the last-fetched draft with the form values before patching", async () => {
    const seen: SeenRequest[] = [];

    stubFetch(async (request) => {
      seen.push({
        method: request.method,
        url: request.url,
        body: request.method === "GET" ? null : await request.clone().json(),
      });

      return jsonResponse({
        data: productResource({
          draftSpec:
            request.method === "GET" ? DRAFT_SPEC : { ...DRAFT_SPEC, powerKw: 68 },
        }),
      });
    });

    const { view, invalidateQueries } = mountHook(() => ({
      product: useProduct(PRODUCT_ID),
      save: useSaveDraftSpec(PRODUCT_ID),
    }));

    // The merge reads the *fetched* draft, so the detail query has to be there.
    await waitFor(() => {
      expect(view.result.current.product.isSuccess).toBe(true);
    });

    let saved: DraftSpec | undefined;

    await act(async () => {
      saved = await view.result.current.save.mutateAsync({
        values: { powerKw: 68, torqueNm: 63, engineCc: null },
      });
    });

    const patch = seen.at(-1);

    expect(patch).toMatchObject({
      method: "PATCH",
      url: `http://api.test/api/products/${PRODUCT_ID}`,
    });

    const sent = (patch?.body as components["schemas"]["ProductPatchRequest"]).data
      .attributes.draftSpec;

    // The three edited fields, including the emptied one.
    expect(sent).toMatchObject({ powerKw: 68, torqueNm: 63, engineCc: null });
    // Everything the form does not show survives the full-object replace.
    expect(sent).toMatchObject({
      cylinders: 4,
      tankCapacityL: 16.5,
      abs: false,
      extra: { frame: "Steel tube" },
      sourceHints: { powerKw: "Wikipedia infobox" },
      extractedAt: "2026-08-25T09:12:00Z",
    });
    // Every frozen field travels, so nothing is silently reset server-side.
    expect(Object.keys(sent ?? {}).sort()).toEqual(Object.keys(DRAFT_SPEC).sort());
    // The stored draft, as the upsert answered with it.
    expect(saved).toMatchObject({ powerKw: 68 });
    // A saved draft changes neither the backlog list nor any operation.
    expect(invalidateQueries.mock.calls).toEqual([
      [{ queryKey: ["products", "detail", PRODUCT_ID] }],
    ]);
  });

  it("starts from an all-null draft when extraction produced none", async () => {
    const seen: SeenRequest[] = [];

    stubFetch(async (request) => {
      seen.push({
        method: request.method,
        url: request.url,
        body: request.method === "GET" ? null : await request.clone().json(),
      });

      return jsonResponse({ data: productResource() });
    });

    const { view } = mountHook(() => ({
      product: useProduct(PRODUCT_ID),
      save: useSaveDraftSpec(PRODUCT_ID),
    }));

    await waitFor(() => {
      expect(view.result.current.product.isSuccess).toBe(true);
    });

    await act(async () => {
      await view.result.current.save.mutateAsync({ values: { engineCc: 599 } });
    });

    const sent = (seen.at(-1)?.body as components["schemas"]["ProductPatchRequest"]).data
      .attributes.draftSpec;

    // The upsert path: no draft row exists yet, the save creates one.
    expect(sent).toMatchObject({ engineCc: 599, powerKw: null, extra: {} });
    expect(Object.keys(sent ?? {}).sort()).toEqual(Object.keys(DRAFT_SPEC).sort());
  });

  it("maps a 422 loc tail onto the field that was rejected", async () => {
    stubFetch(() =>
      jsonResponse(
        {
          detail: [
            {
              loc: ["body", "data", "attributes", "draftSpec", "powerKw"],
              msg: "Input should be greater than 0",
              type: "greater_than",
            },
          ],
        },
        { status: 422 },
      ),
    );

    const { view, invalidateQueries } = mountHook(() => useSaveDraftSpec(PRODUCT_ID));

    await act(async () => {
      await expect(
        view.result.current.mutateAsync({ values: { powerKw: -5 } }),
      ).rejects.toBeInstanceOf(SaveDraftSpecError);
    });

    expect(view.result.current.error).toMatchObject({
      status: 422,
      validationFields: ["powerKw"],
    });
    // A failed write must not invalidate: nothing changed server-side.
    expect(invalidateQueries).not.toHaveBeenCalled();
  });

  it("leaves the fields empty for an error document without a loc", async () => {
    stubFetch(() =>
      jsonResponse({ errors: [{ status: "404", code: "not-found", detail: "gone" }] }, {
        status: 404,
      }),
    );

    const { view } = mountHook(() => useSaveDraftSpec(PRODUCT_ID));

    await act(async () => {
      await expect(
        view.result.current.mutateAsync({ values: { engineCc: 599 } }),
      ).rejects.toBeInstanceOf(SaveDraftSpecError);
    });

    // Nothing to pin the failure on: the form shows its general error instead.
    expect(view.result.current.error).toMatchObject({
      status: 404,
      validationFields: [],
    });
  });
});

describe("useRejectImage", () => {
  it("patches the image status and invalidates the three affected caches", async () => {
    const seen: SeenRequest[] = [];

    stubFetch(async (request) => {
      seen.push({
        method: request.method,
        url: request.url,
        body: await request.clone().json(),
      });

      return jsonResponse({
        data: imageResource("01IMAGELATESTRUN000000001", { status: "rejected" }),
      });
    });

    const { view, invalidateQueries } = mountHook(() => useRejectImage());

    await act(async () => {
      await view.result.current.mutateAsync({
        imageId: "01IMAGELATESTRUN000000001",
        productId: PRODUCT_ID,
      });
    });

    expect(seen).toEqual([
      {
        method: "PATCH",
        url: "http://api.test/api/product-images/01IMAGELATESTRUN000000001",
        body: {
          data: { type: "product-images", attributes: { status: "rejected" } },
        },
      },
    ]);
    expect(view.result.current.data).toMatchObject({ status: "rejected" });
    // The write also announces `product.updated` server-side, hence all three.
    expect(invalidateQueries.mock.calls).toEqual([
      [{ queryKey: ["products"] }],
      [{ queryKey: ["operations"] }],
      [{ queryKey: ["productImages"] }],
    ]);
  });

  it("reports an illegal image transition as a ProductError", async () => {
    stubFetch(() =>
      jsonResponse(
        {
          errors: [
            { status: "422", code: "invalid-transition", detail: "rejected → rejected" },
          ],
        },
        { status: 422 },
      ),
    );

    const { view, invalidateQueries } = mountHook(() => useRejectImage());

    await act(async () => {
      await expect(
        view.result.current.mutateAsync({
          imageId: "01IMAGELATESTRUN000000001",
          productId: PRODUCT_ID,
        }),
      ).rejects.toBeInstanceOf(ProductError);
    });

    expect(view.result.current.error).toMatchObject({
      status: 422,
      code: "invalid-transition",
    });
    expect(invalidateQueries).not.toHaveBeenCalled();
  });
});
