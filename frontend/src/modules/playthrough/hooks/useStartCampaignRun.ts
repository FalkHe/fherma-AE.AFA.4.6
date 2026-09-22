// The "Select a campaign" dialog's one write (sprint 007/09 WI1, AC2/AC3) —
// `POST /api/v1/playthrough/campaign`. The uniqueness constraint behind this
// endpoint is per-run, not per-campaign-per-player (sprint brief's "API
// facts"), so starting the same campaign twice needs no special handling
// here: it simply creates a second run.
//
// `invalidateQueries` (not `setQueryData`) on success — `CampaignRunRead`
// (this mutation's result) and `CampaignRunSummaryRead` (the dashboard's
// list shape) are different shapes, so there is no value here to splice into
// that cache. The invalidated refetch is left to run in the background
// (never awaited) and lands while the player is on the run screen, since the
// dashboard that requested it is still mounted underneath.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import { api } from "../../../core/api/client";
import { unwrap, type ApiFailure } from "../../../core/api/errors";
import type { components } from "../../../api/schema";

export type CampaignRun = components["schemas"]["CampaignRunRead"];

export function useStartCampaignRun() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  return useMutation<CampaignRun, ApiFailure, string>({
    mutationFn: (campaignId) =>
      unwrap(
        // This route's generated 422 response types as `HTTPValidationError`
        // (schema.d.ts), unlike its 401/403/404, which are wrapped in the
        // shared `ErrorEnvelope` — the same backend-side gap noted in
        // `useRunOverview.ts`. The request body is one required string
        // field, so a 422 never actually fires here; the cast below only
        // narrows the type `unwrap` needs to compile against, it changes no
        // runtime behaviour.
        api.POST("/api/v1/playthrough/campaign", { body: { campaignId } }) as unknown as Promise<{
          data?: CampaignRun;
          error?: components["schemas"]["ErrorEnvelope"];
          response: Response;
        }>,
      ),
    onSuccess: (run) => {
      void queryClient.invalidateQueries({ queryKey: ["runSummaries"] });
      navigate(`/runs/${run.id}`);
    },
  });
}
