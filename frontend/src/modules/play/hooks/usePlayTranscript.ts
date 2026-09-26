// The play screen's transcript read (sprint 010/06 WI1, I4) -- one call to
// the existing events route with `limit: 500` (the whole transcript,
// research.md), mapped through `toTranscriptRows` (I1). Mirrors
// `useRunOverview`'s shape (same `unwrap` call, same isPending/isError/retry
// surface).
//
// `heroName` is a parameter rather than read here a second time: it lives
// on the table read (`heroes[0].name`, ← D9's one hero per run), which the
// caller already holds from `usePlayTable` -- fetching it again from this
// hook would duplicate that network call for no benefit.
import { useQuery, type QueryFunctionContext } from "@tanstack/react-query";

import { api } from "../../../core/api/client";
import { unwrap } from "../../../core/api/errors";
import type { components } from "../../../api/schema";
import { isTurnUnfinished, toPendingPrompt, toTranscriptRows, type EventRead, type PendingPrompt, type TranscriptRow } from "../transcript";

interface TranscriptState {
  rows: TranscriptRow[];
  awaiting: string;
  turnUnfinished: boolean;
  pending: PendingPrompt | null;
}

// Fallback poll while a turn is running (sprint 010/07 WI7 round 2, ← AC2/
// AC4): the notice stream (`useRunNotices.ts`) is meant to be what triggers
// a re-read, but a dropped or delayed tick must not leave the screen
// stalled, so this query also re-reads itself on a plain interval for as
// long as a turn looks like it is still going.
//
// `isSendingRef` is a ref, not a plain boolean, on purpose: `useTakeTurn`
// needs this hook's own `rows` to build its send-time snapshot
// (`PlayRoute.tsx`), so by the time `useTakeTurn`'s `isSending` exists, this
// hook has already been called for the render -- there is no boolean to
// pass in yet. `PlayScreen` syncs `.current` from its own effect
// (`useEffect(() => { isSendingRef.current = isSending }, [isSending])`),
// mirroring `useRunNotices.ts`'s `onTickRef`; `refetchInterval` itself only
// ever runs after render (its own interval timer, or a fetch settling), so
// by the time it reads `.current` the ref has always caught up. Defect A
// round 2's actual fix does not lean on this ref at all -- it is
// `useTakeTurn.ts`'s own `cancelRefetch: true` -- so this poll's own
// staleness tolerance (at most one render late) was never the problem.
export interface IsSendingRef {
  readonly current: boolean;
}

interface UsePlayTranscriptOptions {
  isSendingRef?: IsSendingRef;
  /** Test-only override for the fallback poll's interval. */
  pollIntervalMs?: number;
  /** Test-only override for the read's own deadline (defect A round 2). */
  transcriptTimeoutMs?: number;
}

const DEFAULT_POLL_INTERVAL_MS = 3000;
// The turn route itself may run for a minute or more (sprint brief,
// `useTakeTurn.ts`), but a plain transcript *read* never should -- a read
// that hangs this long is a dead connection, not a slow one. Bounding it
// means a stuck GET can never wedge `onSettled`'s post-turn invalidation
// (`useTakeTurn.ts`) behind it forever; TanStack retries the query itself
// once this deadline fires (`retry` stays at its default).
const DEFAULT_TRANSCRIPT_TIMEOUT_MS = 15000;

type EventsRead = components["schemas"]["EventsRead"];

async function fetchTranscript(
  runId: string,
  heroName: string,
  signal: AbortSignal,
  timeoutMs: number,
): Promise<TranscriptState> {
  const result = await unwrap(
    // Same generated-422-type gap as `useRunOverview.ts`/`usePlayTable.ts` --
    // `run_id` is a required string path segment, so a 422 never actually
    // fires here; the cast only narrows the type `unwrap` needs to compile
    // against, it changes no runtime behaviour.
    //
    // `signal` combines two sources (`AbortSignal.any`, DOM lib, ES2022+):
    // TanStack's own per-fetch signal -- which it aborts itself the moment
    // a newer fetch supersedes this one, e.g. `invalidateQueries({
    // cancelRefetch: true })`, `useTakeTurn.ts`'s post-turn call -- and a
    // plain deadline, so a read with no newer fetch to supersede it (a
    // first load, or a poll tick) still cannot hang forever either.
    api.GET("/api/v1/playthrough/campaign/{run_id}/events", {
      params: { path: { run_id: runId }, query: { limit: 500 } },
      signal: AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)]),
    }) as unknown as Promise<{
      data?: EventsRead;
      error?: components["schemas"]["ErrorEnvelope"];
      response: Response;
    }>,
  );
  const events = result.events as EventRead[];
  return {
    rows: toTranscriptRows(events, heroName),
    awaiting: result.awaiting,
    turnUnfinished: isTurnUnfinished(events),
    pending: toPendingPrompt(events, result.awaiting),
  };
}

export function usePlayTranscript(runId: string, heroName: string, options: UsePlayTranscriptOptions = {}) {
  const {
    isSendingRef,
    pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
    transcriptTimeoutMs = DEFAULT_TRANSCRIPT_TIMEOUT_MS,
  } = options;
  const query = useQuery({
    queryKey: ["transcript", runId],
    queryFn: ({ signal }: QueryFunctionContext) => fetchTranscript(runId, heroName, signal, transcriptTimeoutMs),
    // A function, not a plain interval, so it can read the query's own
    // freshest data (`query.state.data`) rather than the value this hook
    // last returned to its caller -- reading the latter here would be
    // circular, since `turnUnfinished` below is that very return value
    // (TanStack v5: `refetchInterval` receives the `Query` itself).
    //
    // `isSendingRef.current` alone decides "still running" whenever it is
    // true -- deliberately never anded with `awaiting`/`turnUnfinished`
    // (defect A round 2): those two only ever describe the *last landed*
    // read, which is exactly the stale data a wedged invalidation leaves
    // behind while a turn is still out; requiring them as well as
    // `isSending` would make the poll stop covering the one case it exists
    // for.
    refetchInterval: (latest) => {
      const data = latest.state.data;
      const stillRunning = (isSendingRef?.current ?? false) || (data !== undefined && data.awaiting === "none" && data.turnUnfinished);
      return stillRunning ? pollIntervalMs : false;
    },
  });

  return {
    rows: query.data?.rows ?? [],
    awaiting: query.data?.awaiting ?? "none",
    turnUnfinished: query.data?.turnUnfinished ?? false,
    pending: query.data?.pending ?? null,
    isPending: query.isPending,
    isError: query.isError,
    retry: () => {
      void query.refetch();
    },
  };
}
