// Sprint 010/06 WI1, I4. `usePlayTranscript` reads the events route with
// `limit: 500` and hands the result through `toTranscriptRows` -- these
// tests check the read/query-key/awaiting wiring, not the mapping itself
// (covered by `transcript.test.ts`).
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

import { createQueryClient } from "../../../core/queryClient";
import { mockRoute } from "../../../test/network";
import { usePlayTranscript } from "./usePlayTranscript";

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={createQueryClient()}>{children}</QueryClientProvider>;
}

describe("usePlayTranscript", () => {
  it("maps the read's events into rows and passes awaiting through", async () => {
    mockRoute("GET", "/api/v1/playthrough/campaign/run-1/events", {
      status: 200,
      body: {
        events: [
          { id: "e1", type: "narration", turnId: "t1", payload: { text: "Once upon a time." }, createdAt: "2026-09-08T21:02:00+00:00" },
        ],
        awaiting: "none",
      },
    });

    const { result } = renderHook(() => usePlayTranscript("run-1", "Rosalind Thorn"), { wrapper });

    await waitFor(() => expect(result.current.isPending).toBe(false));

    expect(result.current.rows).toEqual([
      { kind: "narration", id: "e1", text: "Once upon a time.", at: "2026-09-08T21:02:00+00:00" },
    ]);
    expect(result.current.awaiting).toBe("none");
    expect(result.current.isError).toBe(false);
    expect(result.current.turnUnfinished).toBe(false);
  });

  it("exposes turnUnfinished when the last event is not a narration (I5)", async () => {
    mockRoute("GET", "/api/v1/playthrough/campaign/run-2/events", {
      status: 200,
      body: {
        events: [
          { id: "e1", type: "player_action", turnId: "t1", payload: { text: "I attack." }, createdAt: "2026-09-08T21:02:00+00:00" },
          { id: "e2", type: "roll", turnId: "t1", payload: { kind: "attack", total: 12 }, createdAt: "2026-09-08T21:02:05+00:00" },
        ],
        awaiting: "none",
      },
    });

    const { result } = renderHook(() => usePlayTranscript("run-2", "Rosalind Thorn"), { wrapper });

    await waitFor(() => expect(result.current.isPending).toBe(false));

    expect(result.current.turnUnfinished).toBe(true);
  });

  it("keeps turnUnfinished false while pending", () => {
    mockRoute("GET", "/api/v1/playthrough/campaign/run-3/events", {
      status: 200,
      body: { events: [], awaiting: "none" },
    });

    const { result } = renderHook(() => usePlayTranscript("run-3", "Rosalind Thorn"), { wrapper });

    expect(result.current.isPending).toBe(true);
    expect(result.current.turnUnfinished).toBe(false);
  });

  it("retry recovers from a failed read", async () => {
    let attempts = 0;
    mockRoute("GET", "/api/v1/playthrough/campaign/run-1/events", () => {
      attempts += 1;
      if (attempts === 1) {
        throw new Error("simulated network failure");
      }
      return { status: 200, body: { events: [], awaiting: "none" } };
    });

    const { result } = renderHook(() => usePlayTranscript("run-1", "Rosalind Thorn"), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));

    result.current.retry();

    await waitFor(() => expect(result.current.isError).toBe(false));
    expect(result.current.rows).toEqual([]);
  });
});
