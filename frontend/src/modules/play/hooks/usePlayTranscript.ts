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
import { useQuery } from "@tanstack/react-query";

import { api } from "../../../core/api/client";
import { unwrap } from "../../../core/api/errors";
import type { components } from "../../../api/schema";
import { isTurnUnfinished, toTranscriptRows, type EventRead, type TranscriptRow } from "../transcript";

interface TranscriptState {
  rows: TranscriptRow[];
  awaiting: string;
  turnUnfinished: boolean;
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
// pass in yet. A ref sidesteps that: the caller hands over the same ref
// object on every render (stable identity, so `useQuery` never sees it as a
// changed option) and syncs its `.current` from its own effect once
// `isSending` is known, mirroring `useRunNotices.ts`'s `onTickRef`.
// `refetchInterval` itself only ever runs after render (on the interval
// timer or after a fetch settles), so by the time it reads `.current` the
// ref has always caught up.
export interface IsSendingRef {
  readonly current: boolean;
}

interface UsePlayTranscriptOptions {
  isSendingRef?: IsSendingRef;
  /** Test-only override for the fallback poll's interval. */
  pollIntervalMs?: number;
}

const DEFAULT_POLL_INTERVAL_MS = 3000;

type EventsRead = components["schemas"]["EventsRead"];

async function fetchTranscript(runId: string, heroName: string): Promise<TranscriptState> {
  const result = await unwrap(
    // Same generated-422-type gap as `useRunOverview.ts`/`usePlayTable.ts` --
    // `run_id` is a required string path segment, so a 422 never actually
    // fires here; the cast only narrows the type `unwrap` needs to compile
    // against, it changes no runtime behaviour.
    api.GET("/api/v1/playthrough/campaign/{run_id}/events", {
      params: { path: { run_id: runId }, query: { limit: 500 } },
    }) as unknown as Promise<{
      data?: EventsRead;
      error?: components["schemas"]["ErrorEnvelope"];
      response: Response;
    }>,
  );
  const events = result.events as EventRead[];
  return { rows: toTranscriptRows(events, heroName), awaiting: result.awaiting, turnUnfinished: isTurnUnfinished(events) };
}

export function usePlayTranscript(runId: string, heroName: string, options: UsePlayTranscriptOptions = {}) {
  const { isSendingRef, pollIntervalMs = DEFAULT_POLL_INTERVAL_MS } = options;
  const query = useQuery({
    queryKey: ["transcript", runId],
    queryFn: () => fetchTranscript(runId, heroName),
    // A function, not a plain interval, so it can read the query's own
    // freshest data (`query.state.data`) rather than the value this hook
    // last returned to its caller -- reading the latter here would be
    // circular, since `turnUnfinished` below is that very return value
    // (TanStack v5: `refetchInterval` receives the `Query` itself).
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
    isPending: query.isPending,
    isError: query.isError,
    retry: () => {
      void query.refetch();
    },
  };
}
