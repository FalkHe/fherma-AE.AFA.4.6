/**
 * Network fakes.
 *
 * Tests never talk to a backend, but they do exercise the real request path,
 * including the generated API client. `fetch` is therefore replaced once, by
 * the setup file, with a dispatcher that each test points at its own handler.
 *
 * Replacing it once and up front is not optional: openapi-fetch captures
 * `globalThis.fetch` when the client is created, i.e. while `api/client.ts` is
 * being imported, so a stub installed inside a test would arrive too late.
 */

type FetchHandler = (request: Request) => Response | Promise<Response>;

const refuseRequest: FetchHandler = (request) => {
  throw new Error(
    `Unstubbed ${request.method} ${request.url}: call stubFetch() in the test first.`,
  );
};

let handler: FetchHandler = refuseRequest;

/** Called once per test file, from the setup module. */
export function installFetchStub(): void {
  globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(input, init);

    // `.then` rather than a direct call: a handler that throws must reject the
    // promise, the way a failing fetch does.
    return Promise.resolve().then(() => handler(request));
  };
}

/**
 * Answers every request with `respond`, which receives the outgoing `Request`
 * so a test can assert on the URL, method or body.
 */
export function stubFetch(respond: FetchHandler): void {
  handler = respond;
}

/** Leaves every request hanging, so a loading state stays observable. */
export function stubPendingFetch(): void {
  stubFetch(() => new Promise<Response>(() => undefined));
}

/** Restores the "no test asked for this request" default. */
export function resetFetchStub(): void {
  handler = refuseRequest;
}

/** Builds the JSON response shape the API client expects. */
export function jsonResponse(body: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
}
