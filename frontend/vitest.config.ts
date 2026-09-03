import { defineConfig, mergeConfig } from "vitest/config";

import viteConfig from "./vite.config.ts";

// Derived from the application config so that plugins and any future resolve
// aliases cannot drift between `vite build` and the test run. Vitest prefers
// this file over vite.config.ts, which therefore stays free of test settings.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      env: {
        // The jsdom environment keeps Node's `Request`, which — unlike a
        // browser's — refuses relative URLs. Giving the API client an absolute
        // base mirrors the cross-origin development setup and keeps the client
        // itself untouched by tests.
        VITE_API_URL: "http://api.test",
      },
      // Test APIs are imported explicitly instead of injected, so the app
      // tsconfig needs no extra global type packages.
      globals: false,
      // Spies are undone between tests rather than in each test's teardown.
      restoreMocks: true,
    },
  }),
);
