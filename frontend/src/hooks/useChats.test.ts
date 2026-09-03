import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { components } from "../api/schema";
import { jsonResponse, stubFetch } from "../test/network";

import { ChatError } from "./useChatMessages";
import { useChat, useChats, useCreateChat, useDeleteChat } from "./useChats";

/**
 * The hooks are exercised through the real request path — the generated client
 * against the stubbed `fetch` — because that is where the JSON:API envelope, the
 * page walk and the error mapping live.
 */

type ChatResource = components["schemas"]["ChatResource"];

function chatResource(
  id: string,
  overrides: Partial<components["schemas"]["ChatAttributes"]> = {},
): ChatResource {
  return {
    id,
    type: "chats",
    attributes: {
      title: `Consultation ${id}`,
      activeOperationId: null,
      createdAt: "2026-08-25T09:00:00Z",
      updatedAt: "2026-08-25T09:00:00Z",
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

describe("useChats", () => {
  it("walks every page, so consultation 101 does not disappear", async () => {
    const requestedPages: string[] = [];
    const firstPage = Array.from({ length: 100 }, (_unused, index) =>
      chatResource(`c${index + 1}`),
    );

    stubFetch((request) => {
      const query = new URL(request.url).searchParams;

      requestedPages.push(query.get("page[number]") ?? "");
      expect(query.get("page[size]")).toBe("100");

      return jsonResponse(
        query.get("page[number]") === "1"
          ? { data: firstPage, meta: { totalCount: 101 } }
          : { data: [chatResource("c101")], meta: { totalCount: 101 } },
      );
    });

    const { view } = mountHook(() => useChats());

    await waitFor(() => {
      expect(view.result.current.isSuccess).toBe(true);
    });

    expect(requestedPages).toEqual(["1", "2"]);
    expect(view.result.current.data).toHaveLength(101);
    // Flattened: `id` merged with the resource's attributes.
    expect(view.result.current.data?.at(-1)).toEqual({
      id: "c101",
      title: "Consultation c101",
      activeOperationId: null,
      createdAt: "2026-08-25T09:00:00Z",
      updatedAt: "2026-08-25T09:00:00Z",
    });
  });
});

describe("useChat", () => {
  it("flattens the chat and carries its active operation", async () => {
    stubFetch(() =>
      jsonResponse({
        data: chatResource("c1", { activeOperationId: "01OPERATION0000000000000001" }),
      }),
    );

    const { view } = mountHook(() => useChat("c1"));

    await waitFor(() => {
      expect(view.result.current.isSuccess).toBe(true);
    });

    expect(view.result.current.data?.activeOperationId).toBe(
      "01OPERATION0000000000000001",
    );
  });

  it("reports an unknown or foreign chat as a 404 ChatError", async () => {
    stubFetch(() =>
      jsonResponse(
        { errors: [{ status: "404", code: "not-found", detail: "gone" }] },
        { status: 404 },
      ),
    );

    const { view } = mountHook(() => useChat("c1"));

    await waitFor(() => {
      expect(view.result.current.isError).toBe(true);
    });

    const error = view.result.current.error;

    expect(error).toBeInstanceOf(ChatError);
    expect((error as ChatError).status).toBe(404);
    expect((error as ChatError).code).toBe("not-found");
  });

  it("asks for nothing while the route param is still empty", () => {
    stubFetch(() => {
      throw new Error("The hook must not request chat \"\".");
    });

    const { view } = mountHook(() => useChat(""));

    expect(view.result.current.fetchStatus).toBe("idle");
  });
});

describe("useCreateChat", () => {
  it("posts the strict empty envelope and invalidates the list", async () => {
    let payload: unknown;

    stubFetch(async (request) => {
      payload = await request.json();

      return jsonResponse(
        { data: chatResource("c-new", { activeOperationId: "01OPERATIONGREET000000001" }) },
        { status: 201 },
      );
    });

    const { view, invalidateQueries } = mountHook(() => useCreateChat());
    let created: Awaited<ReturnType<typeof view.result.current.mutateAsync>> | undefined;

    await act(async () => {
      created = await view.result.current.mutateAsync();
    });

    // Empty attributes object, not an omitted one: the endpoint validates it.
    expect(payload).toEqual({ data: { type: "chats", attributes: {} } });
    // The advisor speaks first, so the created chat already has a turn running —
    // the route navigates straight into the typing state.
    expect(created).toMatchObject({
      id: "c-new",
      activeOperationId: "01OPERATIONGREET000000001",
    });
    expect(invalidateQueries.mock.calls).toEqual([[{ queryKey: ["chats"] }]]);
  });
});

describe("useDeleteChat", () => {
  it("treats a 404 as success, because the row is gone either way", async () => {
    stubFetch(() =>
      jsonResponse(
        { errors: [{ status: "404", code: "not-found", detail: "gone" }] },
        { status: 404 },
      ),
    );

    const { view, invalidateQueries } = mountHook(() => useDeleteChat());

    await act(async () => {
      await view.result.current.mutateAsync({ chatId: "c1" });
    });

    expect(view.result.current.isSuccess).toBe(true);
    expect(invalidateQueries.mock.calls).toEqual([[{ queryKey: ["chats"] }]]);
  });

  it("reports any other failure, so the dialog can say so", async () => {
    stubFetch(() =>
      jsonResponse(
        { errors: [{ status: "500", code: "server-error", detail: "boom" }] },
        { status: 500 },
      ),
    );

    const { view } = mountHook(() => useDeleteChat());

    await act(async () => {
      await expect(
        view.result.current.mutateAsync({ chatId: "c1" }),
      ).rejects.toBeInstanceOf(ChatError);
    });
  });
});
