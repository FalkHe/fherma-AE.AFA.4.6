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

/**
 * The `chat-messages` resource: one conversation's timeline plus the one write a
 * customer performs on it.
 *
 * Every request goes through the generated `openapi-fetch` client, so the
 * JSON:API envelopes and every message part are typed from the backend's own
 * schema. The envelope is unwrapped here and nowhere else — components see flat
 * rows.
 *
 * This file also holds **the only optimistic update in the application**
 * (ui-spec §3.2): the user's own outgoing message appears before the server has
 * confirmed it, because a chat composer that waits for a round trip feels
 * broken. Everything else — the advisor's answer, the turn state — is refetched
 * server truth, pushed by SSE invalidation.
 */

/** One retrieved chunk backing an assistant answer (`chat_messages.sources`). */
export type MessageSource = components["schemas"]["MessageSource"];

/**
 * One executed tool call (`chat_messages.tool_calls`).
 *
 * `arguments` and `result` are open objects by design: every tool has its own
 * result schema, and the renderers shape-check what they get, so a tool the
 * frontend predates still renders through the generic fallback.
 */
export type ToolCall = components["schemas"]["ToolCall"];

/**
 * One recommended model (`chat_messages.recommendations`): a write-time
 * snapshot, so a card is self-contained and needs no catalogue read.
 */
export type Recommendation = components["schemas"]["Recommendation"];

/**
 * One message of a conversation: the resource id merged with its attributes.
 *
 * `localId` and `state` are **client-side only** — they exist while the user's
 * own outgoing message is in flight (ui-spec §3.2/§6) and are absent on every row
 * the server delivers. A refetch therefore replaces a confirmed optimistic entry
 * with the server row and the caption falls back to the timestamp.
 */
export type ChatMessage = { id: string } & components["schemas"]["ChatMessageAttributes"] & {
    /** Client-side correlation id of an optimistic outgoing message. */
    localId?: string;
    /** Send state of an optimistic outgoing message. */
    state?: "sending" | "sent" | "failed";
  };

/**
 * A failed chat call, carrying what the screens branch on.
 *
 * Same shape and rationale as `ProductError`: the backend's `detail` is English
 * prose for developers, so the UI decides its own message from the status code
 * (404 → "not found", 409 `response-pending` → a quiet refetch, anything else →
 * "server error"). `code` is the stable application code of a JSON:API domain
 * error and `null` for the shapes that carry none. Never branch on `detail`.
 */
export class ChatError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(status: number, code: string | null = null) {
    super(`Chat request failed with status ${status}`);
    this.name = "ChatError";
    this.status = status;
    this.code = code;
  }
}

/** The two error bodies these endpoints can answer with (see shared-knowledge). */
type ErrorBody =
  | components["schemas"]["ErrorDocument"]
  | components["schemas"]["HTTPValidationError"]
  | undefined;

export function chatError(status: number, body: ErrorBody): ChatError {
  // Domain failures arrive as a JSON:API `errors[]` document; request-validation
  // 422s keep FastAPI's `{"detail": [...]}` shape and therefore have no code.
  const code =
    body !== undefined && "errors" in body && body.errors.length > 0
      ? body.errors[0].code
      : null;

  return new ChatError(status, code);
}

/** Application code of the 409 a genuinely in-flight turn answers with. */
const RESPONSE_PENDING_CODE = "response-pending";

/**
 * Pinned page size — also the server's maximum. A conversation is bounded (the
 * advisor replays it in full every turn), so the hook walks the pages instead of
 * paginating the timeline; without the walk message 101 would silently vanish.
 */
const PAGE_SIZE = 100;

function toChatMessage(
  resource: components["schemas"]["ChatMessageResource"],
): ChatMessage {
  return { id: resource.id, ...resource.attributes };
}

/**
 * `GET /api/chat-messages?filter[chat]=…`, following `meta.totalCount` to the
 * last page. The server's order (`createdAt ASC, id ASC`) is kept untouched: the
 * whole chat UI reads "the last message" and "the newest user message" off the
 * end of this list.
 */
async function listMessages(chatId: string): Promise<ChatMessage[]> {
  const messages: ChatMessage[] = [];

  for (let page = 1; ; page += 1) {
    const { data, error, response } = await apiClient.GET("/api/chat-messages", {
      params: {
        query: {
          "filter[chat]": chatId,
          "page[number]": page,
          "page[size]": PAGE_SIZE,
        },
      },
    });

    if (!response.ok || data === undefined) {
      // An unknown chat and somebody else's answer the same 404 — no existence
      // leak, and the route shows its not-found gate.
      throw chatError(response.status, error);
    }

    messages.push(...data.data.map(toChatMessage));

    // The empty-page guard keeps the loop finite if the timeline changes between
    // two page requests.
    if (messages.length >= data.meta.totalCount || data.data.length === 0) {
      return messages;
    }
  }
}

/**
 * Reconciliation of the optimistic entry with refetched server truth — the
 * mechanism ui-spec §3.2 left to be pinned at wiring time.
 *
 * The server does **not** echo the client's `localId` (a message id is a
 * server-side ULID), so a refetch cannot match rows up. It does not have to: a
 * *confirmed* optimistic entry is already in the fetched list as a real row, so
 * dropping it is exactly right — the bubble stays on screen and its "Seen"
 * caption comes from the turn, not from the entry. Only the entries the server
 * has never seen survive a refetch: one still in flight (`sending`) and, above
 * all, a `failed` one — it holds text the user typed and offers retry/discard,
 * and an advisor reply landing meanwhile must not wipe it.
 */
function withUnsentEntries(
  fetched: ChatMessage[],
  cached: ChatMessage[] | undefined,
): ChatMessage[] {
  const unsent = (cached ?? []).filter(
    (row) => row.state === "sending" || row.state === "failed",
  );

  // Unsent entries are the newest thing in the conversation by definition, so
  // they belong at the end of the timeline.
  return unsent.length === 0 ? fetched : [...fetched, ...unsent];
}

/** `POST /api/chat-messages` — the customer's message, which starts a turn. */
async function sendMessage(chatId: string, body: string): Promise<ChatMessage> {
  const { data, error, response } = await apiClient.POST("/api/chat-messages", {
    body: { data: { type: "chat-messages", attributes: { chatId, body } } },
  });

  if (!response.ok || data === undefined) {
    // 404 for an unknown or foreign chat, 409 `response-pending` when a turn is
    // genuinely in flight, 422 for a body the schema refuses.
    throw chatError(response.status, error);
  }

  return toChatMessage(data.data);
}

/**
 * One conversation's timeline, oldest → newest.
 *
 * Walks every page of `GET /api/chat-messages?filter[chat]=…` and keeps the
 * server's ordering. Unsent optimistic entries survive the refetch
 * (`withUnsentEntries`); everything else is server truth.
 */
export function useChatMessages(chatId: string): UseQueryResult<ChatMessage[], Error> {
  const queryClient = useQueryClient();
  const timelineKey = queryKeys.chatMessages.byChat(chatId);

  return useQuery({
    queryKey: timelineKey,
    queryFn: async () =>
      withUnsentEntries(
        await listMessages(chatId),
        queryClient.getQueryData<ChatMessage[]>(timelineKey),
      ),
    // The route param can be empty for a fraction of a render; asking for the
    // messages of chat "" would answer 400 and show the wrong gate.
    enabled: chatId !== "",
  });
}

/**
 * Sends the user's message — **the one optimistic update in this application**
 * (ui-spec §3.2).
 *
 * `onMutate` appends the outgoing message to the timeline cache immediately, so
 * the bubble is on screen before the request resolves; the caller clears the
 * composer and scrolls. On success the entry is marked `sent` (that *is* the
 * "seen" signal — there is no dedicated event) and both caches are invalidated,
 * so the refetch replaces it with the server row and picks up the chat's new
 * `activeOperationId`. On failure the entry stays put marked `failed`: it holds
 * the text the user typed, and the bubble offers retry (same `localId`, so this
 * replaces rather than duplicates) and discard.
 */
export function useSendMessage(
  chatId: string,
): UseMutationResult<ChatMessage, Error, { body: string; localId: string }> {
  const queryClient = useQueryClient();
  const timelineKey = queryKeys.chatMessages.byChat(chatId);

  function patchEntry(localId: string, patch: Partial<ChatMessage>): void {
    queryClient.setQueryData<ChatMessage[]>(timelineKey, (rows) =>
      rows?.map((row) => (row.localId === localId ? { ...row, ...patch } : row)),
    );
  }

  return useMutation<ChatMessage, Error, { body: string; localId: string }>({
    mutationFn: ({ body }) => sendMessage(chatId, body),
    onMutate: ({ body, localId }) => {
      const optimistic: ChatMessage = {
        id: localId,
        role: "user",
        body,
        toolCalls: [],
        sources: [],
        recommendations: [],
        createdAt: new Date().toISOString(),
        localId,
        state: "sending",
      };

      queryClient.setQueryData<ChatMessage[]>(timelineKey, (rows) => {
        const existing = rows ?? [];

        // A retry re-fires the mutation with the same `localId`: the failed
        // bubble must flip back to "sending" in place, not appear twice.
        return existing.some((row) => row.localId === localId)
          ? existing.map((row) => (row.localId === localId ? optimistic : row))
          : [...existing, optimistic];
      });
    },
    onSuccess: (_created, { localId }) => {
      patchEntry(localId, { state: "sent" });
      void queryClient.invalidateQueries({ queryKey: queryKeys.chatMessages.all });
      // The chat's last activity and its `activeOperationId` both moved.
      void queryClient.invalidateQueries({ queryKey: queryKeys.chats.all });
    },
    onError: (error, { localId }) => {
      // The message was not stored — the bubble keeps the text and offers the
      // way out (ui-spec §3.2 step 3), whatever the status was.
      patchEntry(localId, { state: "failed" });

      if (error instanceof ChatError && error.code === RESPONSE_PENDING_CODE) {
        // A turn the UI did not know about is in flight (the composer guard lost
        // a race): no error dialog, just refetch the chat so the typing state
        // appears and the retry button becomes usable once the advisor is done.
        void queryClient.invalidateQueries({ queryKey: queryKeys.chats.all });
      }
    },
  });
}
