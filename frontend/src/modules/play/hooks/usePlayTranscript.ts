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
import { toTranscriptRows, type EventRead, type TranscriptRow } from "../transcript";

interface TranscriptState {
  rows: TranscriptRow[];
  awaiting: string;
}

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
  return { rows: toTranscriptRows(result.events as EventRead[], heroName), awaiting: result.awaiting };
}

export function usePlayTranscript(runId: string, heroName: string) {
  const query = useQuery({
    queryKey: ["transcript", runId],
    queryFn: () => fetchTranscript(runId, heroName),
  });

  return {
    rows: query.data?.rows ?? [],
    awaiting: query.data?.awaiting ?? "none",
    isPending: query.isPending,
    isError: query.isError,
    retry: () => {
      void query.refetch();
    },
  };
}
