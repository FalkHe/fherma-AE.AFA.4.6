// One query per run, mirroring `useCurrentUser`'s shape (modules/auth/hooks/
// useCurrentUser.ts): an expected non-200 outcome becomes state, not a
// thrown query error, so a screen never has to tell "the run doesn't exist"
// apart from "the request failed". Unlike `useCurrentUser`'s 401, the
// expected outcome here is a 404 (`CampaignRunNotFoundError`, unknown run
// and foreign run alike — sprint 007/05 research.md) — and, per decision,
// an `unavailable: true` 200 (the run's pinned campaign content is gone)
// reads identically, so both collapse into the same `notFound` flag here
// rather than being told apart on the route.
import { useQuery } from "@tanstack/react-query";

import { api } from "../../../core/api/client";
import { unwrap, type ApiFailure } from "../../../core/api/errors";
import type { components } from "../../../api/schema";

export type RunOverview = components["schemas"]["CampaignRunOverviewRead"];
export type RunMember = components["schemas"]["CampaignRunMemberRead"];

interface RunOverviewState {
  overview: RunOverview | null;
  notFound: boolean;
}

async function fetchRunOverview(runId: string): Promise<RunOverviewState> {
  try {
    const overview = await unwrap(
      // This route's generated 422 response types as `HTTPValidationError`
      // (schema.d.ts:905-912), unlike every auth endpoint's 422, which is
      // wrapped in the shared `ErrorEnvelope` (e.g. schema.d.ts:632-639) —
      // a backend-side gap outside this frontend work item's scope. `run_id`
      // is a required string path segment, so a 422 never actually fires
      // here; the cast below only narrows the type `unwrap` needs to
      // compile against, it changes no runtime behaviour.
      api.GET("/api/v1/playthrough/runs/{run_id}/overview", { params: { path: { run_id: runId } } }) as unknown as Promise<{
        data?: RunOverview;
        error?: components["schemas"]["ErrorEnvelope"];
        response: Response;
      }>,
    );
    if (overview.unavailable) {
      return { overview: null, notFound: true };
    }
    return { overview, notFound: false };
  } catch (error) {
    const failure = error as ApiFailure;
    if (failure.status === 404) {
      return { overview: null, notFound: true };
    }
    throw failure;
  }
}

export function useRunOverview(runId: string) {
  const query = useQuery({
    queryKey: ["runOverview", runId],
    queryFn: () => fetchRunOverview(runId),
  });

  return {
    overview: query.data?.overview ?? null,
    isPending: query.isPending,
    isError: query.isError,
    notFound: query.data?.notFound ?? false,
    retry: () => {
      void query.refetch();
    },
  };
}
