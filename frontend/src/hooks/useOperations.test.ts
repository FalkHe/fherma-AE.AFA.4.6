import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import type { components } from "../api/schema";
import { jsonResponse, stubFetch } from "../test/network";

import { useLatestOperationsByEntity } from "./useOperations";

type OperationResource = components["schemas"]["OperationResource"];

function operationResource(
  id: string,
  overrides: Partial<components["schemas"]["OperationAttributes"]> = {},
): OperationResource {
  return {
    id,
    type: "operations",
    attributes: {
      type: "ingestion",
      status: "running",
      progress: 40,
      message: "Fetching sources (2/6)",
      error: null,
      entityType: "motorbike",
      entityId: "bike-1",
      createdAt: "2026-08-25T09:00:00Z",
      startedAt: "2026-08-25T09:00:04Z",
      finishedAt: null,
      ...overrides,
    },
  };
}

function mountHook() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  function Providers({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  }

  return renderHook(() => useLatestOperationsByEntity(), { wrapper: Providers });
}

describe("useLatestOperationsByEntity", () => {
  it("keeps the newest operation per entity and skips unattached ones", async () => {
    stubFetch(() =>
      jsonResponse({
        data: [
          operationResource("op-old", {
            createdAt: "2026-08-25T08:00:00Z",
            status: "failed",
            progress: 15,
          }),
          operationResource("op-new", { createdAt: "2026-08-25T09:00:00Z" }),
          operationResource("op-other", { entityId: "bike-2", status: "queued" }),
          // Not attached to a motorbike (an `embeddings.rebuild` run, say):
          // nothing can look it up, so it must not enter the map.
          operationResource("op-global", {
            entityType: null,
            entityId: null,
            type: "embeddings.rebuild",
          }),
        ],
        meta: { totalCount: 4 },
      }),
    );

    const view = mountHook();

    await waitFor(() => {
      expect(view.result.current.isSuccess).toBe(true);
    });

    const latest = view.result.current.data;

    expect(latest?.size).toBe(2);
    expect(latest?.get("bike-1")).toMatchObject({
      id: "op-new",
      status: "running",
      progress: 40,
      message: "Fetching sources (2/6)",
    });
    expect(latest?.get("bike-2")?.status).toBe("queued");
  });

  it("walks every page before reducing", async () => {
    const requestedPages: string[] = [];

    stubFetch((request) => {
      const query = new URL(request.url).searchParams;

      requestedPages.push(query.get("page[number]") ?? "");

      return jsonResponse({
        data:
          query.get("page[number]") === "1"
            ? Array.from({ length: 100 }, (_unused, index) =>
                operationResource(`op-${index}`, { entityId: `bike-${index}` }),
              )
            : [operationResource("op-100", { entityId: "bike-100" })],
        meta: { totalCount: 101 },
      });
    });

    const view = mountHook();

    await waitFor(() => {
      expect(view.result.current.isSuccess).toBe(true);
    });

    expect(requestedPages).toEqual(["1", "2"]);
    expect(view.result.current.data?.get("bike-100")).toMatchObject({ id: "op-100" });
  });

  it("surfaces a failed request as an error", async () => {
    stubFetch(() => jsonResponse({ detail: "Not authenticated" }, { status: 401 }));

    const view = mountHook();

    await waitFor(() => {
      expect(view.result.current.isError).toBe(true);
    });

    expect(view.result.current.error?.message).toContain("401");
  });
});
