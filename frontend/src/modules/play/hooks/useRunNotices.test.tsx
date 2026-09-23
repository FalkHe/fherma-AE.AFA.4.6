// Sprint 010/07 WI4, I4 ← AC2/AC5. jsdom has no `EventSource` at all, so
// this installs a fake in its place (`vi.stubGlobal`) that records every
// instance opened against it -- the hook is driven entirely through that
// fake's `onmessage`/`onerror` handlers and `close()` calls, exactly as a
// real `EventSource` would drive it.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";

import { useRunNotices } from "./useRunNotices";

class FakeEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;

  readonly CONNECTING = FakeEventSource.CONNECTING;
  readonly OPEN = FakeEventSource.OPEN;
  readonly CLOSED = FakeEventSource.CLOSED;

  readonly url: string;
  readonly withCredentials: boolean;
  readyState = FakeEventSource.OPEN;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  closed = false;

  constructor(url: string | URL, init?: EventSourceInit) {
    this.url = String(url);
    this.withCredentials = init?.withCredentials ?? false;
    instances.push(this);
  }

  addEventListener(): void {
    // Unused by the hook under test; present only so the fake stands in
    // for the full `EventSource` shape.
  }

  removeEventListener(): void {}

  close(): void {
    this.closed = true;
    this.readyState = FakeEventSource.CLOSED;
  }

  emitMessage(data: string): void {
    this.onmessage?.(new MessageEvent("message", { data }));
  }

  emitFatalError(): void {
    this.readyState = FakeEventSource.CLOSED;
    this.onerror?.(new Event("error"));
  }

  emitTransientError(): void {
    // A close the browser will itself reconnect from -- `readyState` stays
    // `CONNECTING`, not `CLOSED`.
    this.readyState = FakeEventSource.CONNECTING;
    this.onerror?.(new Event("error"));
  }
}

let instances: FakeEventSource[] = [];

beforeEach(() => {
  instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("useRunNotices", () => {
  it("opens the stream for the given run with the session cookie", () => {
    renderHook(() => useRunNotices("run-1", () => {}));

    expect(instances).toHaveLength(1);
    expect(instances[0].url).toContain("/api/v1/playthrough/campaign/run-1/stream");
    expect(instances[0].withCredentials).toBe(true);
  });

  it("ticks on an updated message", () => {
    const onTick = vi.fn();
    renderHook(() => useRunNotices("run-1", onTick));

    instances[0].emitMessage(JSON.stringify({ type: "updated", id: "evt-1" }));

    expect(onTick).toHaveBeenCalledTimes(1);
  });

  it("stays silent on a message that is not an update", () => {
    const onTick = vi.fn();
    renderHook(() => useRunNotices("run-1", onTick));

    instances[0].emitMessage(JSON.stringify({ type: "something-else" }));

    expect(onTick).not.toHaveBeenCalled();
  });

  it("stays silent on malformed data", () => {
    const onTick = vi.fn();
    renderHook(() => useRunNotices("run-1", onTick));

    instances[0].emitMessage("not json");

    expect(onTick).not.toHaveBeenCalled();
  });

  it("stays silent on a transient error the browser will itself reconnect from", () => {
    vi.useFakeTimers();
    const onTick = vi.fn();
    renderHook(() => useRunNotices("run-1", onTick));

    instances[0].emitTransientError();
    vi.advanceTimersByTime(5000);

    expect(instances).toHaveLength(1);
  });

  it("reopens after a fatal close", () => {
    vi.useFakeTimers();
    renderHook(() => useRunNotices("run-1", () => {}));

    expect(instances).toHaveLength(1);
    instances[0].emitFatalError();
    expect(instances[0].closed).toBe(true);
    expect(instances).toHaveLength(1);

    vi.advanceTimersByTime(2000);

    expect(instances).toHaveLength(2);
    expect(instances[1].url).toContain("/api/v1/playthrough/campaign/run-1/stream");
  });

  it("calls back through the latest onTick without resubscribing", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ onTick }) => useRunNotices("run-1", onTick), {
      initialProps: { onTick: first },
    });

    rerender({ onTick: second });
    expect(instances).toHaveLength(1);

    instances[0].emitMessage(JSON.stringify({ type: "updated" }));

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("closes the stream on unmount", () => {
    const { unmount } = renderHook(() => useRunNotices("run-1", () => {}));

    unmount();

    expect(instances[0].closed).toBe(true);
  });

  it("closes the old stream and opens a new one when the run id changes", () => {
    const { rerender } = renderHook(({ runId }) => useRunNotices(runId, () => {}), {
      initialProps: { runId: "run-1" },
    });

    rerender({ runId: "run-2" });

    expect(instances).toHaveLength(2);
    expect(instances[0].closed).toBe(true);
    expect(instances[1].url).toContain("/api/v1/playthrough/campaign/run-2/stream");
  });
});
