// The one fetch dispatcher for the whole suite (see setup.ts). openapi-fetch
// captures `globalThis.fetch` when `core/api/client.ts` is evaluated, so this
// must be installed once, before any test module imports that client, and
// never replaced afterwards. Tests register/clear routes on this dispatcher
// instead of re-stubbing `fetch` itself.
//
// `VITE_API_URL` is undefined under vitest, so the client's `baseUrl` is
// undefined and openapi-fetch calls `fetch` with the bare relative path
// (e.g. "/api/v1/auth/sign-in"). This dispatcher matches on the URL's
// `pathname` only (resolved against a dummy base when the input is
// relative), so it treats an absolute and a relative request the same way —
// deliberately, so a test is unaffected by whichever `baseUrl` a future step
// configures.
import { vi } from "vitest";

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface RecordedRequest {
  method: Method;
  path: string;
  /** Header names are lower-cased, matching the `Headers` iteration contract. */
  headers: Record<string, string>;
  body: unknown;
  credentials: RequestCredentials | undefined;
}

export interface StubResponse {
  status: number;
  body?: unknown;
  headers?: Record<string, string>;
}

type Responder = StubResponse | (() => StubResponse | Promise<StubResponse>);

const DUMMY_BASE = "http://test.invalid";

const handlers = new Map<string, Responder[]>();
const requests: RecordedRequest[] = [];

function routeKey(method: string, path: string): string {
  return `${method.toUpperCase()} ${path}`;
}

/**
 * Registers the response(s) for one method+path. Pass an array to answer
 * successive calls to the same route differently (each entry is consumed in
 * order; the last entry sticks for any further call) — needed wherever a
 * test drives more than one request against the same endpoint in sequence.
 */
export function mockRoute(method: Method, path: string, responder: Responder | Responder[]): void {
  const queue = Array.isArray(responder) ? [...responder] : [responder];
  handlers.set(routeKey(method, path), queue);
}

/** A responder that stays pending until `resolve` is called — for asserting an in-flight state. */
export function deferredResponse(): { promise: Promise<StubResponse>; resolve: (value: StubResponse) => void } {
  let resolve!: (value: StubResponse) => void;
  const promise = new Promise<StubResponse>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

export function getRequests(filter?: { method?: Method; path?: string }): RecordedRequest[] {
  return requests.filter(
    (request) =>
      (!filter?.method || request.method === filter.method) &&
      (!filter?.path || request.path === filter.path),
  );
}

export function resetNetwork(): void {
  handlers.clear();
  requests.length = 0;
}

function headersToRecord(init: HeadersInit | undefined): Record<string, string> {
  const record: Record<string, string> = {};
  new Headers(init).forEach((value, key) => {
    record[key] = value;
  });
  return record;
}

function parseBody(rawBody: BodyInit | null | undefined): unknown {
  if (typeof rawBody !== "string") {
    return undefined;
  }
  try {
    return JSON.parse(rawBody);
  } catch {
    return rawBody;
  }
}

export function installFetchMock(): void {
  const dispatch: typeof fetch = async (input, init) => {
    const isRequestObject = typeof input === "object" && input !== null && "url" in input;
    const url = isRequestObject ? (input as Request).url : String(input);
    const method = (
      init?.method ?? (isRequestObject ? (input as Request).method : "GET")
    ).toUpperCase() as Method;
    const pathname = new URL(url, DUMMY_BASE).pathname;
    const headers = headersToRecord(init?.headers ?? (isRequestObject ? (input as Request).headers : undefined));
    const body = parseBody(init?.body);
    const credentials = init?.credentials ?? (isRequestObject ? (input as Request).credentials : undefined);

    requests.push({ method, path: pathname, headers, body, credentials });

    const key = routeKey(method, pathname);
    const queue = handlers.get(key);
    if (!queue || queue.length === 0) {
      // Loud on purpose (D24 / step-0.1 §6.6): a missing stub must fail the
      // test, not be swallowed as `common:errors.network`.
      throw new Error(
        `Unstubbed request: ${method} ${pathname}. Call mockRoute("${method}", "${pathname}", …) before rendering.`,
      );
    }
    const responder = queue.length > 1 ? queue.shift()! : queue[0];
    const result = typeof responder === "function" ? await responder() : responder;

    return new Response(result.body === undefined ? null : JSON.stringify(result.body), {
      status: result.status,
      headers: { "content-type": "application/json", ...result.headers },
    });
  };

  vi.stubGlobal("fetch", dispatch);
}
