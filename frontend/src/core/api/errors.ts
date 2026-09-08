// Normalises any failure from `core/api/client.ts` into `{ code, status }`
// (step-0.1.md §6.2): the server's error envelope of §5.1 when the request
// completed, or the synthetic NETWORK code when `fetch` itself rejected.
import type { components } from "../../api/schema";

export interface ApiFailure {
  code: string;
  status: number;
}

type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];

interface ClientResult<T> {
  data?: T;
  error?: ErrorEnvelope;
  response: Response;
}

/** Awaits an `openapi-fetch` call and returns its data, or throws an `ApiFailure`. */
export async function unwrap<T>(result: Promise<ClientResult<T>>): Promise<T> {
  let outcome: ClientResult<T>;
  try {
    outcome = await result;
  } catch {
    throw networkFailure();
  }
  if (outcome.error) {
    const failure: ApiFailure = { code: outcome.error.error.code, status: outcome.response.status };
    throw failure;
  }
  return outcome.data as T;
}

function networkFailure(): ApiFailure {
  return { code: "NETWORK", status: 0 };
}
