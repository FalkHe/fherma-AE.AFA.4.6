import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";

import { queryKeys } from "../queryKeys";

/**
 * The server-push side of this UI: one Server-Sent Events stream that turns
 * backend state changes into TanStack Query invalidations.
 *
 * Nothing in this application polls. Long operations (ingestion above all)
 * report progress by updating rows in PostgreSQL, the backend fans those
 * changes out over `GET /api/events`, and the only thing the browser does with
 * an event is drop the affected caches — the ordinary query then refetches
 * through the typed API client. That keeps event payloads to ids (they are
 * never trusted as content) and means every screen shows live data without any
 * component knowing that SSE exists.
 *
 * Native `EventSource` is deliberate: session authentication is a cookie, so
 * no custom headers are needed, and the browser owns the reconnect loop
 * (including `Last-Event-ID`). Hand-rolled backoff would only fight it.
 */

/**
 * Same base as the API client: empty in production (same origin, so this is
 * exactly `/api/events`), the backend origin during development, where Vite
 * serves the SPA from a different port.
 */
const eventsUrl = `${import.meta.env.VITE_API_URL ?? ""}/api/events`;

/** The event names the backend emits on the `app_events` channel. */
type ServerEventName =
  | "operation.updated"
  | "product.updated"
  | "document.updated"
  | "chat.message.created";

/**
 * Which caches each event always invalidates.
 *
 * `operation.updated` deliberately touches `["operations"]` only: progress
 * ticks arrive several times per ingestion and must not drag the product list
 * along with them. A product's own status flip comes as `product.updated`.
 *
 * `chat.message.created` touches both chat caches: the advisor's answer joins
 * the timeline, and the consultation's last activity and `activeOperationId`
 * (the typing indicator's only input) move with it.
 *
 * `product.updated` reaches the customer catalogue as well: an approval or an
 * unpublish changes which models the catalogue shows, and the two namespaces are
 * separate caches on purpose (admin and customer see different payloads).
 */
const INVALIDATIONS: Record<ServerEventName, readonly (readonly string[])[]> = {
  "operation.updated": [queryKeys.operations.all],
  "product.updated": [queryKeys.products.all, queryKeys.catalogue.all],
  "document.updated": [queryKeys.documents.all, queryKeys.products.all],
  "chat.message.created": [queryKeys.chatMessages.all, queryKeys.chats.all],
};

/**
 * Refetched after a reconnect: events emitted while the stream was down are
 * gone for good, so the caches that drive the live screens are restored
 * wholesale rather than left showing a frozen past. The chat caches are in here
 * because a reply that landed during the gap must appear on reconnect — without
 * a reload, and without polling.
 */
const RECONNECT_INVALIDATIONS: readonly (readonly string[])[] = [
  queryKeys.products.all,
  queryKeys.operations.all,
  queryKeys.chats.all,
  queryKeys.chatMessages.all,
  queryKeys.catalogue.all,
  queryKeys.manufacturers.all,
];

/** `entity_type` of an operation answering a consultation turn. */
const CHAT_ENTITY_TYPE = "chat";

/**
 * The one field of the one payload this listener reads.
 *
 * Event payloads carry ids only and are never trusted as content, so parsing is
 * normally unnecessary — every mapping above invalidates a whole prefix. The
 * exception is `operation.updated`: it is emitted for every operation in the
 * system, and the customer chat cannot read `/api/operations` (that endpoint is
 * admin-only, deliberately), so an operation on a *chat* has to move the
 * `chats` cache instead, where the pointer the UI reads actually lives.
 */
function entityTypeOf(event: Event): string | null {
  if (!(event instanceof MessageEvent) || typeof event.data !== "string") {
    return null;
  }

  try {
    const payload: unknown = JSON.parse(event.data);

    if (typeof payload === "object" && payload !== null && "entityType" in payload) {
      const entityType = (payload as { entityType: unknown }).entityType;

      return typeof entityType === "string" ? entityType : null;
    }
  } catch {
    // A malformed payload is not worth a broken screen: the static mapping above
    // already ran, so the worst case is one cache not being refreshed.
  }

  return null;
}

/**
 * Prefixes an event invalidates only for some payloads — see `entityTypeOf`.
 */
function conditionalInvalidations(
  name: ServerEventName,
  event: Event,
): readonly (readonly string[])[] {
  if (name === "operation.updated" && entityTypeOf(event) === CHAT_ENTITY_TYPE) {
    return [queryKeys.chats.all];
  }

  return [];
}

// Connection state lives in the module, not in the hook's component: layouts
// render a "live updates are down" warning, and they must be able to read the
// state without owning (and therefore duplicating) the EventSource.
let connected = false;
const statusListeners = new Set<() => void>();

function setConnected(next: boolean): void {
  if (connected === next) {
    return;
  }

  connected = next;

  for (const listener of statusListeners) {
    listener();
  }
}

function subscribeToStatus(listener: () => void): () => void {
  statusListeners.add(listener);

  return () => {
    statusListeners.delete(listener);
  };
}

function getStatusSnapshot(): boolean {
  return connected;
}

/**
 * Opens the event stream for as long as the calling component is mounted, and
 * invalidates queries as events arrive.
 *
 * Mount this exactly once, in the authenticated shell: a second instance would
 * mean a second server-side LISTEN connection and duplicate refetches. Unmount
 * closes the stream, which is what keeps a sign-out from leaving an
 * authenticated stream open behind the login screen.
 */
export function useServerEvents(): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    // `withCredentials` is what carries the session cookie on the
    // cross-origin development setup; same-origin requests send it anyway.
    const source = new EventSource(eventsUrl, { withCredentials: true });

    function invalidate(prefixes: readonly (readonly string[])[]): void {
      for (const prefix of prefixes) {
        void queryClient.invalidateQueries({ queryKey: prefix });
      }
    }

    // Whether the current `open` is a reconnect rather than the first
    // connection — only the former lost events and needs the blanket refetch.
    let reconnecting = false;

    function handleOpen(): void {
      setConnected(true);

      if (reconnecting) {
        reconnecting = false;
        invalidate(RECONNECT_INVALIDATIONS);
      }
    }

    function handleError(): void {
      // No reconnect logic here on purpose: the browser either retries by
      // itself (network blip) or gave up because the response was not a valid
      // stream (no session, endpoint missing). Both cases are simply "not
      // live" as far as the UI is concerned.
      reconnecting = true;
      setConnected(false);
    }

    const eventListeners = Object.entries(INVALIDATIONS).map(([name, prefixes]) => {
      const eventName = name as ServerEventName;
      const listener = (event: Event): void => {
        invalidate(prefixes);
        invalidate(conditionalInvalidations(eventName, event));
      };

      source.addEventListener(name, listener);

      return { name, listener };
    });

    source.addEventListener("open", handleOpen);
    source.addEventListener("error", handleError);

    return () => {
      for (const { name, listener } of eventListeners) {
        source.removeEventListener(name, listener);
      }

      source.removeEventListener("open", handleOpen);
      source.removeEventListener("error", handleError);
      source.close();
      setConnected(false);
    };
  }, [queryClient]);
}

/**
 * Whether the event stream is currently connected, for the layouts that warn
 * about stale data. Readable from anywhere — it reflects the single stream
 * `useServerEvents` owns, and reports `false` while nothing is mounted.
 */
export function useServerEventsStatus(): { connected: boolean } {
  const isConnected = useSyncExternalStore(
    subscribeToStatus,
    getStatusSnapshot,
    getStatusSnapshot,
  );

  return { connected: isConnected };
}
