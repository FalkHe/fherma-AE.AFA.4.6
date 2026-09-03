import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { components } from "../api/schema";
import { jsonResponse, stubFetch } from "../test/network";

import {
  ProductError,
  useCreateProduct,
  useProducts,
  useTransitionProduct,
  type Product,
} from "./useProducts";

/**
 * The hooks are exercised through the real request path — the generated client
 * against the stubbed `fetch` — because that is where the JSON:API envelope, the
 * page walk and the error mapping live.
 */

type ProductResource = components["schemas"]["ProductResource"];

function productResource(
  id: string,
  overrides: Partial<components["schemas"]["ProductAttributes"]> = {},
): ProductResource {
  return {
    id,
    type: "products",
    attributes: {
      name: `Model ${id}`,
      slug: `model-${id}`,
      manufacturer: null,
      modelName: null,
      yearFrom: null,
      yearTo: null,
      status: "backlog",
      draftSpec: null,
      verifiedSpec: null,
      createdAt: "2026-08-25T09:00:00Z",
      updatedAt: "2026-08-25T09:00:00Z",
      queryName: `Model ${id}`,
      buildingline: null,
      typeCodes: [],
      variants: [],
      suggestion: null,
      ...overrides,
    },
  };
}

function listDocument(data: ProductResource[], totalCount: number) {
  return { data, meta: { totalCount } };
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

/** The prefixes every write has to invalidate, in the order the hooks fire them. */
const WRITE_INVALIDATIONS = [
  [{ queryKey: ["products"] }],
  [{ queryKey: ["operations"] }],
];

describe("useProducts", () => {
  it("walks every page, so row 101 does not disappear", async () => {
    const requestedPages: string[] = [];
    const firstPage = Array.from({ length: 100 }, (_unused, index) =>
      productResource(`p${index + 1}`),
    );

    stubFetch((request) => {
      const query = new URL(request.url).searchParams;

      requestedPages.push(query.get("page[number]") ?? "");
      expect(query.get("page[size]")).toBe("100");

      return jsonResponse(
        query.get("page[number]") === "1"
          ? listDocument(firstPage, 101)
          : listDocument([productResource("p101")], 101),
      );
    });

    const { view } = mountHook(() => useProducts());

    await waitFor(() => {
      expect(view.result.current.isSuccess).toBe(true);
    });

    expect(requestedPages).toEqual(["1", "2"]);
    expect(view.result.current.data).toHaveLength(101);
    // Flattened: `id` merged with the resource's attributes.
    expect(view.result.current.data?.at(-1)).toMatchObject({
      id: "p101",
      name: "Model p101",
      status: "backlog",
    });
  });

  it("sends filter[status] only when a filter is active", async () => {
    const urls: string[] = [];

    stubFetch((request) => {
      urls.push(request.url);

      return jsonResponse(listDocument([], 0));
    });

    const filtered = mountHook(() => useProducts("in_review"));

    await waitFor(() => {
      expect(filtered.view.result.current.isSuccess).toBe(true);
    });

    const unfiltered = mountHook(() => useProducts());

    await waitFor(() => {
      expect(unfiltered.view.result.current.isSuccess).toBe(true);
    });

    expect(urls[0]).toContain("filter[status]=in_review");
    expect(urls[1]).not.toContain("filter");
  });

  it("reports a failed list request as a ProductError with its code", async () => {
    stubFetch(() =>
      jsonResponse(
        { errors: [{ status: "400", code: "invalid-filter", detail: "nope" }] },
        { status: 400 },
      ),
    );

    const { view } = mountHook(() => useProducts());

    await waitFor(() => {
      expect(view.result.current.isError).toBe(true);
    });

    const error = view.result.current.error;

    expect(error).toBeInstanceOf(ProductError);
    expect(error).toMatchObject({ status: 400, code: "invalid-filter" });
  });
});

describe("useCreateProduct", () => {
  it("posts a JSON:API create document and invalidates both caches", async () => {
    const seen: { method: string; url: string; body: unknown }[] = [];

    stubFetch(async (request) => {
      seen.push({
        method: request.method,
        url: request.url,
        body: await request.clone().json(),
      });

      return jsonResponse({ data: productResource("new-1") }, { status: 201 });
    });

    const { view, invalidateQueries } = mountHook(() => useCreateProduct());
    let created: Product | undefined;

    await act(async () => {
      created = await view.result.current.mutateAsync({ name: "Suzuki GSR 600" });
    });

    expect(seen).toEqual([
      {
        method: "POST",
        url: "http://api.test/api/products",
        body: {
          data: { type: "products", attributes: { name: "Suzuki GSR 600" } },
        },
      },
    ]);
    // Flattened resource: the created row is what the caller receives.
    expect(created).toMatchObject({ id: "new-1", status: "backlog" });
    expect(invalidateQueries.mock.calls).toEqual(WRITE_INVALIDATIONS);
  });

  it("maps a duplicate slug to status 409 and code duplicate-model", async () => {
    stubFetch(() =>
      jsonResponse(
        {
          errors: [
            { status: "409", code: "duplicate-model", detail: "slug taken" },
          ],
        },
        { status: 409 },
      ),
    );

    const { view, invalidateQueries } = mountHook(() => useCreateProduct());

    await act(async () => {
      await expect(
        view.result.current.mutateAsync({ name: "Honda CB500F" }),
      ).rejects.toBeInstanceOf(ProductError);
    });

    expect(view.result.current.error).toMatchObject({
      status: 409,
      code: "duplicate-model",
    });
    // A failed write must not invalidate: nothing changed server-side.
    expect(invalidateQueries).not.toHaveBeenCalled();
  });

  it("leaves the code null for a request-validation 422", async () => {
    stubFetch(() =>
      jsonResponse({ detail: [{ loc: ["body", "name"], msg: "x", type: "y" }] }, {
        status: 422,
      }),
    );

    const { view } = mountHook(() => useCreateProduct());

    await act(async () => {
      await expect(view.result.current.mutateAsync({ name: " " })).rejects.toThrow();
    });

    expect(view.result.current.error).toMatchObject({ status: 422, code: null });
  });
});

describe("useTransitionProduct", () => {
  it("patches the status and invalidates both caches", async () => {
    const seen: { method: string; url: string; body: unknown }[] = [];

    stubFetch(async (request) => {
      seen.push({
        method: request.method,
        url: request.url,
        body: await request.clone().json(),
      });

      return jsonResponse({
        data: productResource("p1", { status: "ingesting" }),
      });
    });

    const { view, invalidateQueries } = mountHook(() => useTransitionProduct());

    await act(async () => {
      await view.result.current.mutateAsync({ id: "p1", status: "ingesting" });
    });

    expect(seen).toEqual([
      {
        method: "PATCH",
        url: "http://api.test/api/products/p1",
        body: { data: { type: "products", attributes: { status: "ingesting" } } },
      },
    ]);
    expect(view.result.current.data).toMatchObject({ status: "ingesting" });
    expect(invalidateQueries.mock.calls).toEqual(WRITE_INVALIDATIONS);
  });

  it("maps an illegal transition to status 422 and code invalid-transition", async () => {
    stubFetch(() =>
      jsonResponse(
        {
          errors: [
            { status: "422", code: "invalid-transition", detail: "backlog → approved" },
          ],
        },
        { status: 422 },
      ),
    );

    const { view } = mountHook(() => useTransitionProduct());

    await act(async () => {
      await expect(
        view.result.current.mutateAsync({ id: "p1", status: "approved" }),
      ).rejects.toBeInstanceOf(ProductError);
    });

    expect(view.result.current.error).toMatchObject({
      status: 422,
      code: "invalid-transition",
    });
  });
});
