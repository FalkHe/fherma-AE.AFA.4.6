// Taking a turn (sprint 010/07 WI6, I6 ← AC1/AC2/AC3). One write --
// `POST …/game/runs/{runId}/turn` -- fired the moment the player sends
// their words, never awaited by the caller before showing them: `send`
// snapshots the row ids already on screen, opens `pending` with the text
// and a timestamp taken here (the wire's `player_action` row carries no
// timestamp of its own until the transcript re-read lands it, ← I6), and
// only then fires the mutation. `PlayRoute` appends `pending` to `rows`
// itself (README.md "Surface") so the player's row is on screen before any
// network round-trip completes.
//
// `pending` clears itself two ways, both by design: once the real
// `player_action` row lands in `rows` (a `player` row whose id was not in
// the snapshot -- the echo of what was just sent), or when the mutation
// settles at all, success or error alike. The second guards against a
// failed request leaving a ghost row on screen forever with nothing to
// clear it, since a failed turn never writes a `player_action` event for
// the first branch to ever match.
//
// The turn route is synchronous and may run for a minute or more (sprint
// brief) -- its response body is never rendered, only used to end the
// mutation's own pending state; everything the player actually sees during
// that wait comes from the transcript re-read this triggers on settle
// (`invalidateQueries`, `cancelRefetch: false` -- an in-flight read from the
// notice stream's own tick is left to finish rather than restarted).
import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../../../core/api/client";
import { unwrap, type ApiFailure } from "../../../core/api/errors";
import type { components } from "../../../api/schema";
import type { TranscriptRow } from "../transcript";

export type TurnRead = components["schemas"]["TurnRead"];

export interface PendingTurn {
  text: string;
  at: string;
}

interface UseTakeTurnArgs {
  runId: string;
  rows: TranscriptRow[];
}

export function useTakeTurn({ runId, rows }: UseTakeTurnArgs) {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingTurn | null>(null);
  // The row ids on screen at the moment `send` was called -- read in the
  // effect below to tell the real, just-landed `player_action` row apart
  // from one that was already there before this turn started.
  const sentBeforeRef = useRef<Set<string>>(new Set());

  const mutation = useMutation<TurnRead, ApiFailure, string>({
    mutationFn: (text) =>
      unwrap(api.POST("/api/v1/game/runs/{run_id}/turn", { params: { path: { run_id: runId } }, body: { text } })),
    onSettled: () => {
      setPending(null);
      // `cancelRefetch` is `invalidateQueries`'s second argument (`InvalidateOptions`,
      // installed `@tanstack/query-core` types) -- not a `QueryFilters` field, despite
      // reading like one; passing it inside the first object is a silent no-op the
      // installed types catch as a `tsc` error, not a runtime one.
      void queryClient.invalidateQueries({ queryKey: ["transcript", runId] }, { cancelRefetch: false });
    },
  });

  useEffect(() => {
    if (pending === null) {
      return;
    }
    const landed = rows.some((row) => row.kind === "player" && !sentBeforeRef.current.has(row.id));
    if (landed) {
      setPending(null);
    }
  }, [rows, pending]);

  function send(text: string): void {
    sentBeforeRef.current = new Set(rows.map((row) => row.id));
    setPending({ text, at: new Date().toISOString() });
    mutation.mutate(text);
  }

  return { send, isSending: mutation.isPending, pending };
}
