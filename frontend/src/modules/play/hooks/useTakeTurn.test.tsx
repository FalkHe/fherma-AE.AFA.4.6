// Sprint 010/07 WI6, I6 ← AC1/AC2/AC3. `send`'s own snapshot-then-clear
// bookkeeping is the only logic worth testing here -- the mutation wiring
// itself (CSRF, error envelope) is the shared client's job, already covered
// elsewhere.
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

import { createQueryClient } from "../../../core/queryClient";
import { deferredResponse, getRequests, mockRoute } from "../../../test/network";
import { useTakeTurn } from "./useTakeTurn";
import type { TranscriptRow } from "../transcript";

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={createQueryClient()}>{children}</QueryClientProvider>;
}

function wrapperWith(queryClient: ReturnType<typeof createQueryClient>) {
  return function ({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe("useTakeTurn", () => {
  it("opens pending with the sent text the moment send is called", () => {
    mockRoute("POST", "/api/v1/game/runs/run-1/turn", () => new Promise(() => {}));

    const { result } = renderHook(() => useTakeTurn({ runId: "run-1", rows: [] }), { wrapper });

    act(() => {
      result.current.send("I open the door.");
    });

    expect(result.current.pending).toEqual(
      expect.objectContaining({ text: "I open the door." }),
    );
    expect(result.current.isSending).toBe(true);
  });

  it("clears pending once a player row not in the pre-send snapshot lands in rows", async () => {
    const pendingRequest = deferredResponse();
    mockRoute("POST", "/api/v1/game/runs/run-1/turn", () => pendingRequest.promise);

    const initialRows: TranscriptRow[] = [{ kind: "narration", id: "e1", text: "You stand before a door.", at: "t" }];
    const { result, rerender } = renderHook(({ rows }) => useTakeTurn({ runId: "run-1", rows }), {
      wrapper,
      initialProps: { rows: initialRows },
    });

    act(() => {
      result.current.send("I open the door.");
    });
    expect(result.current.pending).not.toBeNull();

    // The real `player_action` row lands via a transcript re-read, appended
    // to the rows the caller passes back in on the next render.
    const landedRows: TranscriptRow[] = [
      ...initialRows,
      { kind: "player", id: "e2", author: "Rosalind Thorn", text: "I open the door.", at: "t2" },
    ];
    rerender({ rows: landedRows });

    await waitFor(() => expect(result.current.pending).toBeNull());
  });

  it("clears pending and invalidates the transcript when the turn fails, leaving no ghost row", async () => {
    mockRoute("POST", "/api/v1/game/runs/run-1/turn", {
      status: 500,
      body: { error: { code: "SERVER_ERROR", message: "x", details: null } },
    });

    const queryClient = createQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useTakeTurn({ runId: "run-1", rows: [] }), {
      wrapper: wrapperWith(queryClient),
    });

    act(() => {
      result.current.send("I open the door.");
    });
    expect(result.current.pending).not.toBeNull();

    await waitFor(() => expect(result.current.pending).toBeNull());
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["transcript", "run-1"] }, { cancelRefetch: false });
  });

  it("startOpening posts { text: null } and leaves pending null while isSending is true ← AC4", async () => {
    mockRoute("POST", "/api/v1/game/runs/run-1/turn", () => new Promise(() => {}));

    const { result } = renderHook(() => useTakeTurn({ runId: "run-1", rows: [] }), { wrapper });

    act(() => {
      result.current.startOpening();
    });

    // Both the mutation's own `isPending` flag and the dispatcher's recorded
    // request land a microtask after `mutate()` returns, not synchronously
    // within `act` -- `waitFor` settles once React and the mock fetch have
    // both flushed.
    await waitFor(() => expect(result.current.isSending).toBe(true));
    expect(result.current.pending).toBeNull();
    expect(getRequests({ method: "POST", path: "/api/v1/game/runs/run-1/turn" })).toEqual([
      expect.objectContaining({ body: { text: null } }),
    ]);
  });
});
