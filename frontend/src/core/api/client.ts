// The one file that touches the network (step-0.1.md §6.2, architecture.md
// "One HTTP client"). Owns the whole CSRF dance: the token lives in module
// memory only — no browser persistence, no React state — and is re-acquired
// from `GET /api/v1/users/me` on every page load.
import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "../../api/schema";

let csrfToken: string | undefined;

const csrfMiddleware: Middleware = {
  async onRequest({ request }) {
    if (request.method !== "GET" && csrfToken) {
      request.headers.set("X-CSRF-Token", csrfToken);
    }
    return request;
  },
  async onResponse({ response }) {
    const token = response.headers.get("X-CSRF-Token");
    if (token) {
      csrfToken = token;
    }
    return response;
  },
};

export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL,
  credentials: "include",
});

api.use(csrfMiddleware);

export function clearCsrfToken(): void {
  csrfToken = undefined;
}
