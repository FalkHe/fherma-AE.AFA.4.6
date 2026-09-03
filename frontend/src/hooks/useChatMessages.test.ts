import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { components } from "../api/schema";
import { jsonResponse, stubFetch } from "../test/network";

import {
  ChatError,
  useChatMessages,
  useSendMessage,
  type ChatMessage,
} from "./useChatMessages";

/**
 * The timeline hook and the application's one optimistic update, through the real
 * request path: the page walk, the envelope unwrapping, and above all the
 * reconciliation rule — which optimistic entries a refetch drops and which it
 * must keep.
 */

type ChatMessageResource = components["schemas"]["ChatMessageResource"];

const CHAT_ID = "01CHAT00000000000000000001";

function messageResource(
  id: string,
  overrides: Partial<components["schemas"]["ChatMessageAttributes"]> = {},
): ChatMessageResource {
  return {
    id,
    type: "chat-messages",
    attributes: {
      role: "assistant",
      body: `Body of ${id}`,
      toolCalls: [],
      sources: [],
      recommendations: [],
      createdAt: "2026-08-25T09:00:00Z",
      ...overrides,
    },
  };
}

/** A query client whose invalidations really refetch — the reconciliation tests. */
function mountLiveHook<T>(hook: () => T) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  function Providers({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  }

  return { view: renderHook(hook, { wrapper: Providers }), queryClient };
}

/** A query client whose invalidations are recorded instead of performed. */
function mountHook<T>(hook: () => T) {
  const mounted = mountLiveHook(hook);
  const invalidateQueries = vi
    .spyOn(mounted.queryClient, "invalidateQueries")
    .mockResolvedValue(undefined);

  return { ...mounted, invalidateQueries };
}

/** Both hooks together, the way the chat route uses them. */
function useConversation(chatId: string = CHAT_ID) {
  return { messages: useChatMessages(chatId), send: useSendMessage(chatId) };
}

describe("useChatMessages", () => {
  it("walks every page of one conversation, oldest first", async () => {
    const requestedPages: string[] = [];
    const firstPage = Array.from({ length: 100 }, (_unused, index) =>
      messageResource(`m${index + 1}`),
    );

    stubFetch((request) => {
      const query = new URL(request.url).searchParams;

      expect(query.get("filter[chat]")).toBe(CHAT_ID);
      requestedPages.push(query.get("page[number]") ?? "");

      return jsonResponse(
        query.get("page[number]") === "1"
          ? { data: firstPage, meta: { totalCount: 101 } }
          : { data: [messageResource("m101")], meta: { totalCount: 101 } },
      );
    });

    const { view } = mountHook(() => useChatMessages(CHAT_ID));

    await waitFor(() => {
      expect(view.result.current.isSuccess).toBe(true);
    });

    expect(requestedPages).toEqual(["1", "2"]);
    expect(view.result.current.data).toHaveLength(101);
    // Flattened, and the server's order untouched.
    expect(view.result.current.data?.at(-1)).toMatchObject({
      id: "m101",
      role: "assistant",
      body: "Body of m101",
    });
  });

  it("reports a foreign or unknown chat as a 404 ChatError", async () => {
    stubFetch(() =>
      jsonResponse(
        { errors: [{ status: "404", code: "not-found", detail: "gone" }] },
        { status: 404 },
      ),
    );

    const { view } = mountHook(() => useChatMessages(CHAT_ID));

    await waitFor(() => {
      expect(view.result.current.isError).toBe(true);
    });

    expect((view.result.current.error as ChatError).status).toBe(404);
  });
});

describe("useSendMessage", () => {
  it("appends optimistically, then lets the server row replace the entry", async () => {
    const stored: ChatMessageResource[] = [];
    let releasePost: (() => void) | undefined;

    stubFetch(async (request) => {
      if (request.method === "POST") {
        const payload = (await request.json()) as components["schemas"]["ChatMessageCreateRequest"];

        expect(payload.data.attributes.chatId).toBe(CHAT_ID);

        // Held open, so the `sending` state is observable at all.
        await new Promise<void>((resolve) => {
          releasePost = resolve;
        });

        // The server assigns its own id — it never echoes the client's localId.
        const created = messageResource("01MESSAGESERVER000000000001", {
          role: "user",
          body: payload.data.attributes.body,
        });

        stored.push(created);

        return jsonResponse({ data: created }, { status: 201 });
      }

      return jsonResponse({ data: [...stored], meta: { totalCount: stored.length } });
    });

    const { view } = mountLiveHook(() => useConversation());

    await waitFor(() => {
      expect(view.result.current.messages.isSuccess).toBe(true);
    });

    act(() => {
      view.result.current.send.mutate({ body: "Hello", localId: "local-1" });
    });

    // On screen before the request resolves — the whole point of the exemption.
    await waitFor(() => {
      expect(view.result.current.messages.data).toMatchObject([
        { id: "local-1", role: "user", body: "Hello", localId: "local-1", state: "sending" },
      ]);
    });

    act(() => {
      releasePost?.();
    });

    // "Seen" is the successful POST: the entry is marked sent, then the refetch
    // replaces it with the server's row (no duplicate, no localId echo needed).
    await waitFor(() => {
      expect(view.result.current.messages.data).toEqual([
        expect.objectContaining({ id: "01MESSAGESERVER000000000001", body: "Hello" }),
      ]);
    });
    expect(view.result.current.messages.data?.[0].state).toBeUndefined();
  });

  it("marks a failed send and keeps it across a refetch", async () => {
    stubFetch((request) => {
      if (request.method === "POST") {
        return jsonResponse(
          { errors: [{ status: "500", code: "server-error", detail: "boom" }] },
          { status: 500 },
        );
      }

      return jsonResponse({
        data: [messageResource("01MESSAGEADVISOR00000000001")],
        meta: { totalCount: 1 },
      });
    });

    const { view } = mountLiveHook(() => useConversation());

    await waitFor(() => {
      expect(view.result.current.messages.isSuccess).toBe(true);
    });

    await act(async () => {
      await view.result.current.send
        .mutateAsync({ body: "Hello", localId: "local-1" })
        .catch(() => undefined);
    });

    await waitFor(() => {
      expect(view.result.current.messages.data?.at(-1)).toMatchObject({
        localId: "local-1",
        state: "failed",
        body: "Hello",
      });
    });

    // An advisor reply landing meanwhile must not wipe the text the user typed.
    await act(async () => {
      await view.result.current.messages.refetch();
    });

    expect(view.result.current.messages.data?.at(-1)).toMatchObject({
      localId: "local-1",
      state: "failed",
    });
    expect(view.result.current.messages.data).toHaveLength(2);
  });

  it("retries in place rather than adding a second bubble", async () => {
    let attempts = 0;

    stubFetch((request) => {
      if (request.method === "POST") {
        attempts += 1;

        return jsonResponse(
          { errors: [{ status: "500", code: "server-error", detail: "boom" }] },
          { status: 500 },
        );
      }

      return jsonResponse({ data: [], meta: { totalCount: 0 } });
    });

    const { view } = mountLiveHook(() => useConversation());

    await waitFor(() => {
      expect(view.result.current.messages.isSuccess).toBe(true);
    });

    for (let attempt = 0; attempt < 2; attempt += 1) {
      await act(async () => {
        await view.result.current.send
          .mutateAsync({ body: "Hello", localId: "local-1" })
          .catch(() => undefined);
      });
    }

    expect(attempts).toBe(2);
    await waitFor(() => {
      expect(view.result.current.messages.data).toHaveLength(1);
    });
  });

  it("answers a 409 response-pending with a quiet refetch of the chat", async () => {
    stubFetch((request) => {
      if (request.method === "POST") {
        return jsonResponse(
          { errors: [{ status: "409", code: "response-pending", detail: "busy" }] },
          { status: 409 },
        );
      }

      return jsonResponse({ data: [], meta: { totalCount: 0 } });
    });

    const { view, invalidateQueries } = mountHook(() => useConversation());

    await waitFor(() => {
      expect(view.result.current.messages.isSuccess).toBe(true);
    });

    await act(async () => {
      await view.result.current.send
        .mutateAsync({ body: "Hello", localId: "local-1" })
        .catch((error: unknown) => {
          expect((error as ChatError).code).toBe("response-pending");
        });
    });

    // No error surface — the chat is refetched so the turn the client raced with
    // becomes visible; the bubble keeps the text and offers retry.
    expect(invalidateQueries.mock.calls).toEqual([[{ queryKey: ["chats"] }]]);
    await waitFor(() => {
      const rows = view.result.current.messages.data as ChatMessage[];

      expect(rows.at(-1)).toMatchObject({ state: "failed", body: "Hello" });
    });
  });
});
