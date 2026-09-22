// The dashboard's one read (sprint 007/07 WI1, AC1) — `GET
// /api/v1/playthrough/runs`, mirroring `useRunOverview`'s shape (same
// `unwrap` call, same `isPending`/`isError`/`retry` surface). The backend
// already answers newest-first (ULID order, archived included, sprint
// brief's "API facts") — this hook renders that order exactly as received
// and never re-sorts in the browser.
import { useQuery } from "@tanstack/react-query";

import { api } from "../../../core/api/client";
import { unwrap } from "../../../core/api/errors";
import type { components } from "../../../api/schema";

export type RunSummary = components["schemas"]["CampaignRunSummaryRead"];

async function fetchRunSummaries(): Promise<RunSummary[]> {
  return unwrap(api.GET("/api/v1/playthrough/runs", {}));
}

export function useRunSummaries() {
  const query = useQuery({
    queryKey: ["runSummaries"],
    queryFn: fetchRunSummaries,
  });

  return {
    runs: query.data ?? [],
    isPending: query.isPending,
    isError: query.isError,
    retry: () => {
      void query.refetch();
    },
  };
}
