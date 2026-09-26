// Sprint 010/06 WI1, I4. `usePlayTranscript` reads the events route with
// `limit: 500` and hands the result through `toTranscriptRows` -- these
// tests check the read/query-key/awaiting wiring, not the mapping itself
// (covered by `transcript.test.ts`).
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";

import { createQueryClient } from "../../../core/queryClient";
import { getRequests, mockRoute } from "../../../test/network";
import { usePlayTranscript } from "./usePlayTranscript";

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={createQueryClient()}>{children}</QueryClientProvider>;
}

function wrapperWith(queryClient: QueryClient) {
  return function ({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
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
    expect(result.current.pending).toBeNull();
  });

  it("exposes pending, built from the read's events and awaiting marker (← I2)", async () => {
    mockRoute("GET", "/api/v1/playthrough/campaign/run-6/events", {
      status: 200,
      body: {
        events: [
          { id: "q1", type: "question", turnId: "t1", payload: { text: "Take it?", options: ["Yes", "No"] }, createdAt: "2026-09-08T21:02:00+00:00" },
        ],
        awaiting: "answer:q1",
      },
    });

    const { result } = renderHook(() => usePlayTranscript("run-6", "Rosalind Thorn"), { wrapper });

    await waitFor(() => expect(result.current.isPending).toBe(false));

    expect(result.current.pending).toEqual({ kind: "choice", id: "q1", options: ["Yes", "No"] });
  });

  it("keeps pending null while pending", () => {
    mockRoute("GET", "/api/v1/playthrough/campaign/run-7/events", {
      status: 200,
      body: { events: [], awaiting: "none" },
    });

    const { result } = renderHook(() => usePlayTranscript("run-7", "Rosalind Thorn"), { wrapper });

    expect(result.current.isPending).toBe(true);
    expect(result.current.pending).toBeNull();
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

  // Fallback poll (sprint 010/07 WI7 round 2, ← AC2/AC4): a live tick off
  // the notice stream is meant to be what triggers a re-read, but the
  // screen must not depend on it alone -- a transcript that still looks
  // mid-turn (awaiting none, last event not a narration) keeps re-reading
  // itself on its own. `pollIntervalMs` is overridden to a few
  // milliseconds so this does not wait out the real 3s default.
  it("re-reads on a short interval while the last event is not yet the closing narration", async () => {
    mockRoute("GET", "/api/v1/playthrough/campaign/run-4/events", {
      status: 200,
      body: {
        events: [
          { id: "e1", type: "player_action", turnId: "t1", payload: { text: "I attack." }, createdAt: "2026-09-08T21:02:00+00:00" },
        ],
        awaiting: "none",
      },
    });

    renderHook(() => usePlayTranscript("run-4", "Rosalind Thorn", { pollIntervalMs: 20 }), { wrapper });

    await waitFor(() =>
      expect(
        getRequests({ method: "GET", path: "/api/v1/playthrough/campaign/run-4/events" }).length,
      ).toBeGreaterThan(1),
    );
  });

  it("does not re-read once the last event is the closing narration", async () => {
    mockRoute("GET", "/api/v1/playthrough/campaign/run-5/events", {
      status: 200,
      body: {
        events: [
          { id: "e1", type: "narration", turnId: "t1", payload: { text: "Done." }, createdAt: "2026-09-08T21:02:00+00:00" },
        ],
        awaiting: "none",
      },
    });

    const { result } = renderHook(() => usePlayTranscript("run-5", "Rosalind Thorn", { pollIntervalMs: 20 }), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isPending).toBe(false));
    await new Promise((resolve) => setTimeout(resolve, 60));

    expect(getRequests({ method: "GET", path: "/api/v1/playthrough/campaign/run-5/events" }).length).toBe(1);
  });

  // Defect A round 2 (`useTakeTurn.ts`'s `onSettled`, `PlayRoute.tsx`'s own
  // notice-tick invalidation): a read issued before a turn's own narration
  // commits can still be in flight when that turn settles. `cancelRefetch:
  // true` must abort that stale read outright and start a fresh one, rather
  // than folding the invalidation into it and leaving the screen showing
  // whatever the stale read eventually resolves to (or never resolves to,
  // for a truly hung connection).
  it("cancelRefetch: true aborts a stale in-flight read and lands a fresh one instead", async () => {
    mockRoute("GET", "/api/v1/playthrough/campaign/run-8/events", [
      // The initial, already-landed read (TanStack's own `cancelRefetch`
      // only cancels a fetch once the query already holds data from a
      // previous one -- `query.js`'s own `fetch()`: `if (this.state.data
      // !== void 0 && fetchOptions?.cancelRefetch) this.cancel(...)` --
      // exactly the ordinary case here: the transcript was already showing
      // something before the turn that is about to settle was ever sent.
      {
        status: 200,
        body: {
          events: [{ id: "e1", type: "narration", turnId: "t0", payload: { text: "You stand before a door." }, createdAt: "2026-09-08T21:00:00+00:00" }],
          awaiting: "none",
        },
      },
      // The stale read: a poll or notice tick issued before the turn's own
      // narration commits (`cancelRefetch: false`, `PlayRoute.tsx`'s own
      // notice invalidation), never itself settling.
      () => new Promise(() => {}),
      {
        status: 200,
        body: {
          events: [{ id: "e2", type: "narration", turnId: "t1", payload: { text: "The door creaks open." }, createdAt: "2026-09-08T21:02:00+00:00" }],
          awaiting: "none",
        },
      },
    ]);

    const queryClient = createQueryClient();
    const { result } = renderHook(() => usePlayTranscript("run-8", "Rosalind Thorn"), {
      wrapper: wrapperWith(queryClient),
    });

    await waitFor(() =>
      expect(result.current.rows).toEqual([
        { kind: "narration", id: "e1", text: "You stand before a door.", at: "2026-09-08T21:00:00+00:00" },
      ]),
    );

    // A stale read starts (e.g. the notice stream's own tick) and never
    // settles -- `invalidateQueries` itself would never resolve either
    // (its own promise waits out the refetch, `@tanstack/query-core` docs),
    // so this is fired without awaiting it, exactly as `PlayRoute.tsx`'s
    // own notice-tick handler does (`void queryClient.invalidateQueries(...)`).
    act(() => {
      void queryClient.invalidateQueries({ queryKey: ["transcript", "run-8"] }, { cancelRefetch: false });
    });
    await waitFor(() =>
      expect(getRequests({ method: "GET", path: "/api/v1/playthrough/campaign/run-8/events" }).length).toBe(2),
    );

    // Mirrors `useTakeTurn.ts`'s own `onSettled` call exactly.
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["transcript", "run-8"] }, { cancelRefetch: true });
    });

    await waitFor(() =>
      expect(result.current.rows).toEqual([
        { kind: "narration", id: "e2", text: "The door creaks open.", at: "2026-09-08T21:02:00+00:00" },
      ]),
    );
    expect(result.current.isError).toBe(false);
    expect(
      getRequests({ method: "GET", path: "/api/v1/playthrough/campaign/run-8/events" }).length,
    ).toBe(3);
  });
});
