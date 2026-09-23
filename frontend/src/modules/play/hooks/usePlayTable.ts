// The play screen's header/party-rail read (sprint 010/06 WI1, I4) --
// mirrors `useRunOverview`'s shape exactly (same `unwrap` call, same
// isPending/isError/retry surface; a 404 collapses into `notFound` rather
// than a thrown query error, same as that hook).
import { useQuery } from "@tanstack/react-query";

import { api } from "../../../core/api/client";
import { unwrap, type ApiFailure } from "../../../core/api/errors";
import type { components } from "../../../api/schema";

export type PlayTable = components["schemas"]["TableRead"];

interface PlayTableState {
  table: PlayTable | null;
  notFound: boolean;
}

async function fetchPlayTable(runId: string): Promise<PlayTableState> {
  try {
    const table = await unwrap(
      // This route's generated 422 response types as `HTTPValidationError`
      // (schema.d.ts:1326-1334), unlike every auth endpoint's 422, which is
      // wrapped in the shared `ErrorEnvelope` — the same backend-side gap
      // `useRunOverview.ts` casts around. `run_id` is a required string path
      // segment, so a 422 never actually fires here; the cast only narrows
      // the type `unwrap` needs to compile against, it changes no runtime
      // behaviour.
      api.GET("/api/v1/playthrough/runs/{run_id}/table", { params: { path: { run_id: runId } } }) as unknown as Promise<{
        data?: PlayTable;
        error?: components["schemas"]["ErrorEnvelope"];
        response: Response;
      }>,
    );
    return { table, notFound: false };
  } catch (error) {
    const failure = error as ApiFailure;
    if (failure.status === 404) {
      return { table: null, notFound: true };
    }
    throw failure;
  }
}

export function usePlayTable(runId: string) {
  const query = useQuery({
    queryKey: ["playTable", runId],
    queryFn: () => fetchPlayTable(runId),
  });

  return {
    table: query.data?.table ?? null,
    isPending: query.isPending,
    isError: query.isError,
    notFound: query.data?.notFound ?? false,
    retry: () => {
      void query.refetch();
    },
  };
}
