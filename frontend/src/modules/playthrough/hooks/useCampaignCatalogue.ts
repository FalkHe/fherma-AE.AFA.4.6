// The "Select a campaign" dialog's one read (sprint 007/09 WI1, AC1) —
// `GET /api/v1/content/campaigns`, mirroring `useRunSummaries`'s shape (same
// `unwrap` call, same `isPending`/`isError`/`retry` surface).
import { useQuery } from "@tanstack/react-query";

import { api } from "../../../core/api/client";
import { unwrap } from "../../../core/api/errors";
import type { components } from "../../../api/schema";

export type CampaignSummary = components["schemas"]["CampaignSummaryRead"];

async function fetchCampaignCatalogue(): Promise<CampaignSummary[]> {
  return unwrap(api.GET("/api/v1/content/campaigns", {}));
}

export function useCampaignCatalogue() {
  const query = useQuery({
    queryKey: ["campaignCatalogue"],
    queryFn: fetchCampaignCatalogue,
  });

  return {
    campaigns: query.data ?? [],
    isPending: query.isPending,
    isError: query.isError,
    retry: () => {
      void query.refetch();
    },
  };
}
