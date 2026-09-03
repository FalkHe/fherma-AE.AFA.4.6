import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useServerEvents, useServerEventsStatus } from "./useServerEvents";

/**
 * jsdom implements no `EventSource`, which is convenient: the whole stream can
 * be driven from the test instead of a server, and every assertion is about the
 * one thing this hook is responsible for — turning events into invalidations.
 */
class MockEventSource extends EventTarget {
  static instances: MockEventSource[] = [];

  readonly close = vi.fn();
  readonly url: string;
  readonly init: EventSourceInit | undefined;

  constructor(url: string, init?: EventSourceInit) {
    super();
    this.url = url;
    this.init = init;
    MockEventSource.instances.push(this);
  }

  /** Dispatches a lifecycle event (`open` / `error`). */
  emitLifecycle(name: "open" | "error"): void {
    act(() => {
      this.dispatchEvent(new Event(name));
    });
  }

  /** Dispatches a named server event, payload included as the real one has. */
  emitServerEvent(name: string, payload: Record<string, string> = {}): void {
    act(() => {
      this.dispatchEvent(
        new MessageEvent(name, { data: JSON.stringify({ event: name, ...payload }) }),
      );
    });
  }
}

function currentSource(): MockEventSource {
  const source = MockEventSource.instances.at(-1);

  if (source === undefined) {
    throw new Error("The hook opened no EventSource.");
  }

  return source;
}

function mountHook() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const invalidateQueries = vi
    .spyOn(queryClient, "invalidateQueries")
    .mockResolvedValue(undefined);

  function Providers({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  }

  // Both hooks in one render: that is how the layouts use them, and it proves
  // the status store reacts to the stream the other hook owns.
  const view = renderHook(
    () => {
      useServerEvents();

      return useServerEventsStatus();
    },
    { wrapper: Providers },
  );

  return { view, invalidateQueries };
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useServerEvents", () => {
  it("opens the events stream with credentials", () => {
    mountHook();

    expect(currentSource().url).toMatch(/\/api\/events$/);
    expect(currentSource().init).toEqual({ withCredentials: true });
  });

  it("invalidates only the operations cache on operation.updated", () => {
    const { invalidateQueries } = mountHook();

    currentSource().emitServerEvent("operation.updated", {
      operationId: "op-1",
      entityType: "motorbike",
    });

    expect(invalidateQueries.mock.calls).toEqual([[{ queryKey: ["operations"] }]]);
  });

  it("also invalidates the chats cache when the operation works on a chat", () => {
    const { invalidateQueries } = mountHook();

    // The customer UI cannot read `/api/operations` (admin-only), so the turn
    // pointer it renders has to be refetched from the chat resource.
    currentSource().emitServerEvent("operation.updated", {
      operationId: "op-1",
      entityType: "chat",
      entityId: "chat-1",
    });

    expect(invalidateQueries.mock.calls).toEqual([
      [{ queryKey: ["operations"] }],
      [{ queryKey: ["chats"] }],
    ]);
  });

  it("invalidates the timeline and the chat list on chat.message.created", () => {
    const { invalidateQueries } = mountHook();

    currentSource().emitServerEvent("chat.message.created", {
      chatId: "chat-1",
      messageId: "message-1",
      role: "assistant",
    });

    expect(invalidateQueries.mock.calls).toEqual([
      [{ queryKey: ["chatMessages"] }],
      [{ queryKey: ["chats"] }],
    ]);
  });

  it("invalidates the products and catalogue caches on product.updated", () => {
    const { invalidateQueries } = mountHook();

    currentSource().emitServerEvent("product.updated", { productId: "p-1" });

    // An approval or an unpublish changes the customer catalogue too, and the
    // two namespaces are separate caches on purpose.
    expect(invalidateQueries.mock.calls).toEqual([
      [{ queryKey: ["products"] }],
      [{ queryKey: ["catalogue"] }],
    ]);
  });

  it("invalidates documents and products on document.updated", () => {
    const { invalidateQueries } = mountHook();

    currentSource().emitServerEvent("document.updated", { productId: "p-1" });

    expect(invalidateQueries.mock.calls).toEqual([
      [{ queryKey: ["documents"] }],
      [{ queryKey: ["products"] }],
    ]);
  });

  it("does not invalidate anything on the first connection", () => {
    const { invalidateQueries } = mountHook();

    currentSource().emitLifecycle("open");

    expect(invalidateQueries).not.toHaveBeenCalled();
  });

  it("invalidates every live cache after a reconnect", () => {
    const { invalidateQueries } = mountHook();
    const source = currentSource();

    source.emitLifecycle("open");
    source.emitLifecycle("error");
    source.emitLifecycle("open");

    // Events lost during the gap are gone for good — including an advisor reply,
    // which must appear without a reload and without any polling.
    expect(invalidateQueries.mock.calls).toEqual([
      [{ queryKey: ["products"] }],
      [{ queryKey: ["operations"] }],
      [{ queryKey: ["chats"] }],
      [{ queryKey: ["chatMessages"] }],
      [{ queryKey: ["catalogue"] }],
      [{ queryKey: ["manufacturers"] }],
    ]);
  });

  it("reports the connection state through useServerEventsStatus", () => {
    const { view } = mountHook();
    const source = currentSource();

    expect(view.result.current.connected).toBe(false);

    source.emitLifecycle("open");
    expect(view.result.current.connected).toBe(true);

    source.emitLifecycle("error");
    expect(view.result.current.connected).toBe(false);
  });

  it("closes the stream on unmount, so a sign-out leaks nothing", () => {
    const { view } = mountHook();
    const source = currentSource();

    source.emitLifecycle("open");
    view.unmount();

    expect(source.close).toHaveBeenCalledOnce();
    expect(MockEventSource.instances).toHaveLength(1);
  });
});
