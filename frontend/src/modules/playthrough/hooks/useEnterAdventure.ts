// "Start adventure" (sprint 010/08 WI1, AC5) — the run screen's one write
// against the current unplayed adventure row: `POST
// /api/v1/playthrough/campaign/{runId}/adventure`, no body. Modelled on
// `useStartCampaignRun`'s shape, but the interface here is narrower (D12 /
// sprint brief `I1`): the section only ever needs `start`, `isPending` and
// `isError`, never the mutation object itself or its data.
//
// A 409 `ADVENTURE_ACTIVE` (another tab, or a retry racing the first
// success) reads identically to a fresh 201 here — the adventure is under
// way either way, so `mutationFn` swallows exactly that failure and lets
// `onSuccess` run as normal; every other failure (network, 500, …) still
// rejects and becomes `isError`.
//
// `invalidateQueries` for both the run overview and the play table before
// navigating, same "never awaited, lands once the player is on the next
// screen" precedent as `useStartCampaignRun`. `startOpening: true` in the
// navigation state is a one-shot flag the play screen reads and clears
// (sibling work item) — this hook only ever sets it, never reads it back.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import { api } from "../../../core/api/client";
import { unwrap, type ApiFailure } from "../../../core/api/errors";
import type { components } from "../../../api/schema";

type AdventureRun = components["schemas"]["AdventureRunRead"];

export interface EnterAdventureResult {
  start: () => void;
  isPending: boolean;
  isError: boolean;
}

export function useEnterAdventure(runId: string): EnterAdventureResult {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const mutation = useMutation<void, ApiFailure, void>({
    mutationFn: async () => {
      try {
        // This route's generated 422 response types as `HTTPValidationError`
        // (schema.d.ts), unlike its 401/403/404/409, which are wrapped in
        // the shared `ErrorEnvelope` — the same backend-side gap noted in
        // `useRunOverview.ts`. `run_id` is a required string path segment,
        // so a 422 never actually fires here; the cast below only narrows
        // the type `unwrap` needs to compile against, it changes no runtime
        // behaviour.
        await unwrap(
          api.POST("/api/v1/playthrough/campaign/{run_id}/adventure", {
            params: { path: { run_id: runId } },
          }) as unknown as Promise<{
            data?: AdventureRun;
            error?: components["schemas"]["ErrorEnvelope"];
            response: Response;
          }>,
        );
      } catch (error) {
        const failure = error as ApiFailure;
        if (failure.status === 409 && failure.code === "ADVENTURE_ACTIVE") {
          return;
        }
        throw failure;
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["runOverview", runId] });
      void queryClient.invalidateQueries({ queryKey: ["playTable", runId] });
      navigate(`/runs/${runId}/play`, { state: { startOpening: true } });
    },
  });

  return {
    start: () => mutation.mutate(),
    isPending: mutation.isPending,
    isError: mutation.isError,
  };
}
