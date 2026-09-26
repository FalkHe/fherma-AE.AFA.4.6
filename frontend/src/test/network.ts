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

function parseBody(rawBody: string | null | undefined): unknown {
  // An empty string reads identically to "no body" (a GET/HEAD's `Request`
  // still yields "" from `.text()`, below) — treated as `undefined`, not as
  // a JSON-parse failure, so a bodyless request's recorded `body` matches
  // what it was before request objects were read at all.
  if (typeof rawBody !== "string" || rawBody === "") {
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
    // openapi-fetch (`core/api/client.ts`) constructs a `Request` up front
    // and hands it to `fetch(request, requestInitExt)` — the JSON body lives
    // on that `Request`, never in `init.body` (checked against the
    // installed openapi-fetch's own source, not just observed behaviour).
    // `.clone()` before consuming it: nothing downstream still needs
    // `input`'s own body, but cloning is the correct way to read a
    // `Request`'s body without it being a footgun for the next caller.
    const rawBody = isRequestObject ? await (input as Request).clone().text() : ((init?.body ?? null) as string | null);
    const body = parseBody(rawBody);
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
    // Honours an `AbortSignal` passed via `init.signal` or riding along on a
    // `Request` object (`RequestOptions`'s own signal channel) -- needed so
    // a hook that races its own fetch against a deadline (`usePlayTranscript`'s
    // `transcriptTimeoutMs`, or a query TanStack itself aborts on
    // `cancelRefetch: true`) can be exercised without waiting out a real
    // network hang in a test. A responder that never settles (`deferredResponse`
    // left unresolved) rejects the moment the signal fires instead of hanging
    // the test forever.
    const signal = init?.signal ?? (isRequestObject ? (input as Request).signal : undefined);
    const resultPromise = typeof responder === "function" ? responder() : Promise.resolve(responder);
    if (signal?.aborted) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }
    const result = signal
      ? await Promise.race([
          resultPromise,
          new Promise<never>((_resolve, reject) => {
            signal.addEventListener(
              "abort",
              () => reject(new DOMException("The operation was aborted.", "AbortError")),
              { once: true },
            );
          }),
        ])
      : await resultPromise;

    return new Response(result.body === undefined ? null : JSON.stringify(result.body), {
      status: result.status,
      headers: { "content-type": "application/json", ...result.headers },
    });
  };

  vi.stubGlobal("fetch", dispatch);
}
