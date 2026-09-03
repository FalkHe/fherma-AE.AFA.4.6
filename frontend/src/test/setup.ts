/**
 * Test bootstrap, run once per test file (`setupFiles` in vitest.config.ts).
 */

// Registers the DOM matchers (`toBeInTheDocument` and friends) on `expect`,
// and augments vitest's assertion types with them.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import { installFetchStub, resetFetchStub } from "./network";

// jsdom implements no media queries, but MUI's colour-scheme handling calls
// `matchMedia` while resolving the "system" mode. Matching nothing makes that
// resolve to the light scheme, deterministically.
window.matchMedia = (query: string): MediaQueryList => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => undefined,
  removeListener: () => undefined,
  addEventListener: () => undefined,
  removeEventListener: () => undefined,
  dispatchEvent: () => false,
});

// Before the first application module is imported, so that the API client
// binds the fake instead of the real `fetch`.
installFetchStub();

afterEach(() => {
  // Testing Library's automatic cleanup only kicks in with injected globals,
  // which this suite does not use.
  cleanup();
  resetFetchStub();
  // MUI persists an explicit theme mode in localStorage; leaving it behind
  // would leak the choice made by one test into the next.
  window.localStorage.clear();
});
