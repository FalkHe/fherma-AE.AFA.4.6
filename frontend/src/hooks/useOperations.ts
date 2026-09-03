import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import type { components } from "../api/schema";
import { queryKeys } from "../queryKeys";

/**
 * The read-only `operations` resource — the state of every background job, and
 * with it the live progress the admin UI renders.
 *
 * One unfiltered query serves every consumer: the operations table is small, and
 * a single cached list keeps a progress tick to one refetch instead of one per
 * visible model. Refetching is driven exclusively by the SSE listener
 * (`operation.updated` → invalidate `["operations"]`) — there is no polling
 * anywhere.
 */

/**
 * Background-job state: the resource id merged with its attributes, so consumers
 * never reach into `.attributes` (same flattening as `Product`).
 */
export type Operation = { id: string } & components["schemas"]["OperationAttributes"];

/** Pinned page size — also the server's maximum, as for the products list. */
const PAGE_SIZE = 100;

function toOperation(resource: components["schemas"]["OperationResource"]): Operation {
  return { id: resource.id, ...resource.attributes };
}

/**
 * `GET /api/operations`, following `meta.totalCount` to the last page.
 *
 * Failures throw a plain `Error` on purpose: no screen branches on why the
 * operations list is unavailable (a row simply renders no progress cell), so this
 * hook deliberately exports no error type of its own. The one exception is
 * `AdminBacklogRoute`, which branches on `isError` (never the error value) to
 * show a "progress could not be loaded" warning above the table.
 */
async function listOperations(): Promise<Operation[]> {
  const operations: Operation[] = [];

  for (let page = 1; ; page += 1) {
    const { data, response } = await apiClient.GET("/api/operations", {
      params: { query: { "page[number]": page, "page[size]": PAGE_SIZE } },
    });

    if (!response.ok || data === undefined) {
      throw new Error(`Operations request failed with status ${response.status}`);
    }

    operations.push(...data.data.map(toOperation));

    if (operations.length >= data.meta.totalCount || data.data.length === 0) {
      return operations;
    }
  }
}

/**
 * Reduces the list to the newest operation per referenced entity, so a row or a
 * page can look up "what is happening to this model" by id.
 */
function latestByEntity(operations: Operation[]): Map<string, Operation> {
  const latest = new Map<string, Operation>();

  for (const operation of operations) {
    if (operation.entityId === null) {
      continue;
    }

    const known = latest.get(operation.entityId);

    if (known === undefined || known.createdAt < operation.createdAt) {
      latest.set(operation.entityId, operation);
    }
  }

  return latest;
}

export function useLatestOperationsByEntity(): UseQueryResult<
  Map<string, Operation>,
  Error
> {
  return useQuery({
    queryKey: queryKeys.operations.list(),
    queryFn: listOperations,
    // Module-level function: a `select` defined inline would be a new reference
    // on every render and rebuild the Map each time.
    select: latestByEntity,
  });
}
