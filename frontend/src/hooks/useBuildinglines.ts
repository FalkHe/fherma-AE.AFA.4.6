import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { queryKeys } from "../queryKeys";

/**
 * A manufacturer's distinct `buildingline` values — the identity panel's drift
 * guard (display-spec §6.2): it is what stops "GS", "gs" and "G S" from all
 * existing as separate families.
 *
 * `GET /api/manufacturers/{id}/buildinglines` (landed by backend step 6.20,
 * ui-spec §8 API-5) answers `{"data": string[]}` (`BuildinglinesDocument`) —
 * wired through the generated `apiClient` since step 6.27.
 */

async function listBuildinglines(manufacturerId: string): Promise<string[]> {
  const { data, response } = await apiClient.GET(
    "/api/manufacturers/{manufacturer_id}/buildinglines",
    { params: { path: { manufacturer_id: manufacturerId } } },
  );

  if (!response.ok || data === undefined) {
    throw new Error(`Buildingline options request failed with status ${response.status}`);
  }

  return data.data;
}

/**
 * A manufacturer's buildingline options, refetched whenever the selected
 * manufacturer changes. Disabled while no manufacturer is selected — the
 * identity panel renders the field itself `disabled` in that state (ui-spec
 * §1.2), it does not render an empty, freely-typable `Autocomplete`.
 */
export function useBuildinglines(
  manufacturerId: string | null,
): UseQueryResult<string[], Error> {
  return useQuery({
    queryKey: queryKeys.buildinglines.byManufacturer(manufacturerId ?? ""),
    queryFn: () => listBuildinglines(manufacturerId ?? ""),
    enabled: manufacturerId !== null,
    // Near-static, like useManufacturers.
    staleTime: 5 * 60_000,
  });
}
