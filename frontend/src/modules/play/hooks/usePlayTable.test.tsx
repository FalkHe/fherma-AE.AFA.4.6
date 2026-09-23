// Sprint 010/06 WI1, I4. Mirrors `useRunOverview`'s own read/notFound/retry
// behaviour, over the table route instead of the overview one.
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

import { createQueryClient } from "../../../core/queryClient";
import { mockRoute } from "../../../test/network";
import { usePlayTable } from "./usePlayTable";

const TABLE = {
  runId: "run-1",
  runTitle: null,
  runStatus: "active",
  campaignTitle: "Greenhollow",
  adventure: { id: "a1", runId: "ar1", title: "Goblins of Greenhollow", status: "active" as const },
  scene: { id: "s1", name: "The Village Green" },
  heroes: [],
};

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={createQueryClient()}>{children}</QueryClientProvider>;
}

describe("usePlayTable", () => {
  it("returns the table once the read resolves", async () => {
    mockRoute("GET", "/api/v1/playthrough/runs/run-1/table", { status: 200, body: TABLE });

    const { result } = renderHook(() => usePlayTable("run-1"), { wrapper });

    expect(result.current.isPending).toBe(true);
    await waitFor(() => expect(result.current.isPending).toBe(false));

    expect(result.current.table).toEqual(TABLE);
    expect(result.current.notFound).toBe(false);
    expect(result.current.isError).toBe(false);
  });

  it("collapses a 404 into notFound rather than isError", async () => {
    mockRoute("GET", "/api/v1/playthrough/runs/missing/table", {
      status: 404,
      body: { error: { code: "NOT_FOUND", message: "x", details: null } },
    });

    const { result } = renderHook(() => usePlayTable("missing"), { wrapper });

    await waitFor(() => expect(result.current.isPending).toBe(false));

    expect(result.current.notFound).toBe(true);
    expect(result.current.table).toBeNull();
    expect(result.current.isError).toBe(false);
  });

  it("retry recovers from a failed read", async () => {
    let attempts = 0;
    mockRoute("GET", "/api/v1/playthrough/runs/run-1/table", () => {
      attempts += 1;
      if (attempts === 1) {
        throw new Error("simulated network failure");
      }
      return { status: 200, body: TABLE };
    });

    const { result } = renderHook(() => usePlayTable("run-1"), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));

    result.current.retry();

    await waitFor(() => expect(result.current.table).toEqual(TABLE));
  });
});
