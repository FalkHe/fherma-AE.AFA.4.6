import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { apiClient } from "../api/client";
import type { components } from "../api/schema";
import { queryKeys } from "../queryKeys";

import { chatError } from "./useChatMessages";

/**
 * The `chats` resource: the signed-in customer's consultations, plus the two
 * writes the list screen performs on them.
 *
 * Every request goes through the generated `openapi-fetch` client, so the
 * JSON:API envelopes (`data`/`attributes`/`meta`) are typed from the backend's
 * own schema. The envelope is unwrapped here and nowhere else — components see
 * flat rows.
 *
 * Nothing here updates optimistically (the one exemption lives in
 * `useChatMessages`): creating and deleting await the server and then
 * invalidate, so the list always renders refetched server truth. Owner scoping
 * is server-side — there is no client-side filter to forget.
 *
 * `ChatError` is defined in the sibling `useChatMessages.ts` and re-exported by
 * it; the error builder is imported from there so both resources produce one
 * error shape (one direction only, no cycle).
 */

/**
 * One consultation: the resource id merged with its attributes.
 *
 * `activeOperationId` is the **only** source of the "advisor is replying" state:
 * `/api/operations` is admin-only and the customer UI never reads it.
 * `updatedAt` doubles as last activity — the server bumps it on every appended
 * message and sorts the list by it, descending. There is no status column.
 */
export type Chat = { id: string } & components["schemas"]["ChatAttributes"];

/**
 * Pinned page size — also the server's maximum. A customer has a handful of
 * consultations, so the hook walks the pages instead of paginating the list;
 * without the walk row 101 would silently disappear.
 */
const PAGE_SIZE = 100;

function toChat(resource: components["schemas"]["ChatResource"]): Chat {
  return { id: resource.id, ...resource.attributes };
}

/** `GET /api/chats`, following `meta.totalCount` to the last page. */
async function listChats(): Promise<Chat[]> {
  const chats: Chat[] = [];

  for (let page = 1; ; page += 1) {
    const { data, error, response } = await apiClient.GET("/api/chats", {
      params: { query: { "page[number]": page, "page[size]": PAGE_SIZE } },
    });

    if (!response.ok || data === undefined) {
      throw chatError(response.status, error);
    }

    // The server's order is the pinned `-updatedAt` (last activity first) and is
    // kept as delivered — the list renders it row for row.
    chats.push(...data.data.map(toChat));

    // The empty-page guard is what keeps this loop finite if a row is deleted
    // between two page requests and `totalCount` stays ahead of what is left.
    if (chats.length >= data.meta.totalCount || data.data.length === 0) {
      return chats;
    }
  }
}

/** `GET /api/chats/{id}` — the resource carrying the turn pointer. */
async function getChat(chatId: string): Promise<Chat> {
  const { data, error, response } = await apiClient.GET("/api/chats/{chat_id}", {
    params: { path: { chat_id: chatId } },
  });

  if (!response.ok || data === undefined) {
    // Unknown id, foreign owner and deleted row all answer 404 — no existence
    // leak, and the route shows one not-found gate for all three.
    throw chatError(response.status, error);
  }

  return toChat(data.data);
}

/** `POST /api/chats` — the strict empty envelope the endpoint requires. */
async function createChat(): Promise<Chat> {
  const { data, error, response } = await apiClient.POST("/api/chats", {
    body: { data: { type: "chats", attributes: {} } },
  });

  if (!response.ok || data === undefined) {
    throw chatError(response.status, error);
  }

  return toChat(data.data);
}

/** `DELETE /api/chats/{id}` — a soft delete server-side. */
async function deleteChat(chatId: string): Promise<void> {
  const { error, response } = await apiClient.DELETE("/api/chats/{chat_id}", {
    params: { path: { chat_id: chatId } },
  });

  // A 404 counts as success: the row the user asked to be rid of is gone either
  // way (already deleted, or never theirs), and the list invalidation below
  // makes the screen agree.
  if (!response.ok && response.status !== 404) {
    throw chatError(response.status, error);
  }
}

/**
 * The signed-in user's consultations, last activity first.
 *
 * Refreshes itself: an advisor reply landing in any conversation arrives as an
 * SSE invalidation of this cache, so rows reorder and the "replying…" hint
 * disappears without a reload.
 */
export function useChats(): UseQueryResult<Chat[], Error> {
  return useQuery({
    queryKey: queryKeys.chats.list(),
    queryFn: listChats,
  });
}

/**
 * One consultation — the resource that carries `activeOperationId`, i.e. the
 * input the chat view derives its turn state from (ui-spec §3.3).
 */
export function useChat(chatId: string): UseQueryResult<Chat, Error> {
  return useQuery({
    queryKey: queryKeys.chats.detail(chatId),
    queryFn: () => getChat(chatId),
    // The route param can be empty for a fraction of a render; asking for chat
    // "" would answer 404 and show the wrong gate.
    enabled: chatId !== "",
  });
}

/**
 * Starts a consultation (`POST /api/chats`, empty attributes object).
 *
 * A chat is only ever created by the explicit "Ask the advisor" button, never on
 * page load, and the 201 already carries `activeOperationId` set: the advisor
 * opens the conversation with a greeting and the first interview question, so the
 * chat view lands directly in the typing state and the greeting arrives over SSE.
 * Navigating to the new chat belongs to the route, which owns the URL.
 */
export function useCreateChat(): UseMutationResult<Chat, Error, void> {
  const queryClient = useQueryClient();

  return useMutation<Chat, Error, void>({
    mutationFn: createChat,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.chats.all });
    },
  });
}

/**
 * Deletes a consultation (`DELETE /api/chats/{id}` — a soft delete server-side).
 *
 * There is no restore affordance: the row is kept in the database, but bringing
 * it back is not a UI feature. The confirmation dialog lives in the list route.
 * Deleting emits no SSE event — only the owner sees this list, so their own
 * invalidation is enough.
 */
export function useDeleteChat(): UseMutationResult<void, Error, { chatId: string }> {
  const queryClient = useQueryClient();

  return useMutation<void, Error, { chatId: string }>({
    mutationFn: ({ chatId }) => deleteChat(chatId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.chats.all });
    },
  });
}
