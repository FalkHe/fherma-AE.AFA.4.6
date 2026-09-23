// Live-update subscription for a running playthrough (sprint 010/07 WI4,
// I4 ← AC2/AC5). The server streams `GET
// /api/v1/playthrough/campaign/{runId}/stream` as `text/event-stream`:
// `data: {"type":"updated","id":"<eventId>"}` when a new event was
// recorded, `: keepalive` comment lines otherwise (never delivered to
// `onmessage` -- SSE comments carry no `data:` field), and the server
// closes the connection after about five minutes.
//
// This cannot go through the shared `openapi-fetch` client (`core/api/client.ts`)
// -- that client speaks request/response, not a long-lived stream -- so it
// opens the browser's own `EventSource` directly, built the same way that
// client reads its base URL (`import.meta.env.VITE_API_URL`) so both hit the
// same origin in dev, where the API is cross-origin from the frontend.
// `withCredentials: true` sends the session cookie; no CSRF header is needed
// for a `GET`.
//
// `EventSource` reconnects on its own after an ordinary server close (its
// built-in retry). It does *not* reconnect after a fatal close -- one its
// own `error` handler reports via `readyState === EventSource.CLOSED` --
// so this reopens it itself, after a short delay, whenever that happens.
import { useEffect, useRef } from "react";

// How long to wait before reopening a fatally-closed stream. Short enough
// that a dropped connection recovers well within AC2's "a few seconds",
// long enough not to hammer the server if it is closing every attempt
// immediately (e.g. while the API is down).
const RECONNECT_DELAY_MS = 2000;

interface RunNoticeMessage {
  type: string;
}

function isUpdatedNotice(raw: string): boolean {
  try {
    const parsed = JSON.parse(raw) as unknown;
    return (
      typeof parsed === "object" &&
      parsed !== null &&
      (parsed as RunNoticeMessage).type === "updated"
    );
  } catch {
    return false;
  }
}

export function useRunNotices(runId: string, onTick: () => void): void {
  // Kept in a ref so callers may pass a fresh closure every render without
  // the subscribing effect below resubscribing on every render too. Synced
  // in its own effect, not during render -- refs are only safe to write
  // outside of render (event handlers, effects).
  const onTickRef = useRef(onTick);
  useEffect(() => {
    onTickRef.current = onTick;
  });

  useEffect(() => {
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    const open = () => {
      if (cancelled) {
        return;
      }
      const base = import.meta.env.VITE_API_URL ?? "";
      const url = `${base}/api/v1/playthrough/campaign/${runId}/stream`;
      const es = new EventSource(url, { withCredentials: true });

      es.onmessage = (event) => {
        if (isUpdatedNotice(event.data)) {
          onTickRef.current();
        }
      };

      es.onerror = () => {
        if (es.readyState === EventSource.CLOSED) {
          es.close();
          reconnectTimer = setTimeout(open, RECONNECT_DELAY_MS);
        }
      };

      source = es;
    };

    open();

    return () => {
      cancelled = true;
      if (reconnectTimer !== undefined) {
        clearTimeout(reconnectTimer);
      }
      source?.close();
    };
  }, [runId]);
}
