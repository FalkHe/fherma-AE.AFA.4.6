import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

import { installFetchMock, resetNetwork } from "./network";

// jsdom has no `matchMedia`. MUI's `colorSchemes` + `cssVariables` setup
// (core/theme.ts) queries it to detect the operating-system colour scheme;
// without a stub that throws on every render, everywhere.
if (typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

// `VITE_API_URL` is undefined under vitest (step-0.1.md §6.6's own wording),
// so `core/api/client.ts` builds `createClient({ baseUrl: import.meta.env.VITE_API_URL, … })`
// with an empty `baseUrl`. That is not merely "requests are relative", as
// §6.6 frames the open question: Node's `Request`/`URL` constructors — unlike
// a browser's, which resolve a schema-relative URL against
// `document.baseURI` — refuse a path with no base at all.
// `new Request("/api/v1/...")` throws `TypeError: Failed to parse URL`
// *synchronously, before `fetch` is ever called*. `core/api/errors.ts`'s
// `unwrap()` (`catch { throw networkFailure() }`) swallows that thrown
// TypeError exactly like a real network failure, so — unfixed — every single
// request in this suite would render as `common:errors.network`,
// indistinguishable from the case actually under test. Setting it here, once,
// before any test module can import `core/api/client.ts`, gives openapi-fetch
// an absolute base to resolve against; `createClient()` reads
// `import.meta.env.VITE_API_URL` once, at module evaluation, so this must run
// first. This is the "define the variable in the vitest env" half of §6.6's
// choice — the dispatcher below still matches on `pathname` alone, so it is
// unaffected by whichever `baseUrl` a later step configures.
(import.meta.env as unknown as Record<string, string>).VITE_API_URL = "http://test.invalid";

// Installed once, at module load, before any test file imports
// `core/api/client.ts` — openapi-fetch captures `globalThis.fetch` at import
// time, so a per-test install would be too late (D24 / step-0.1 §6.6).
installFetchMock();

afterEach(() => {
  cleanup();
  resetNetwork();
});
