import createClient from "openapi-fetch";

import { queryClient } from "../queryClient";
import type { paths } from "./schema";

/**
 * Typed HTTP client for the backend API.
 *
 * Every path, parameter and response body is inferred from `schema.d.ts`,
 * which is generated from the backend's own OpenAPI document (`pnpm
 * generate:api`). Hand-written request/response types are therefore never
 * needed — and a backend change that the frontend has not followed shows up as
 * a type error rather than a runtime surprise.
 */

// Cross-origin in development (Vite on :5173 calling the API on :8000), same
// origin in production. Missing here means "same origin", which is the correct
// production default.
const baseUrl = import.meta.env.VITE_API_URL ?? "";

export const apiClient = createClient<paths>({
  baseUrl,
  // Session authentication is cookie-based (see architecture.md), so the
  // cookie must ride along on cross-origin development calls as well. Set as
  // a client default rather than in the middleware below because `credentials`
  // is immutable on an already-constructed `Request`: mutating it would mean
  // rebuilding every request object, including ones carrying a body.
  credentials: "include",
});

/** Methods that never change state, and therefore need no CSRF token. */
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

const CSRF_COOKIE_NAME = "csrf_token";
const CSRF_HEADER_NAME = "X-CSRF-Token";

/**
 * Reads the CSRF cookie the backend sets at login. It is deliberately not
 * `HttpOnly` (see shared-knowledge *Cookies & CSRF*) precisely so this can be
 * echoed back in a header: the double-submit comparison is what a cross-site
 * form post cannot reproduce.
 */
function readCsrfCookie(): string | null {
  const prefix = `${CSRF_COOKIE_NAME}=`;

  for (const entry of document.cookie.split("; ")) {
    if (entry.startsWith(prefix)) {
      return decodeURIComponent(entry.slice(prefix.length));
    }
  }

  return null;
}

apiClient.use({
  onRequest({ request }) {
    if (SAFE_METHODS.has(request.method)) {
      return undefined;
    }

    const csrfToken = readCsrfCookie();

    if (csrfToken === null) {
      // No cookie means no session to protect; let the request go and let the
      // backend answer 401/403 rather than inventing a client-side failure.
      return undefined;
    }

    request.headers.set(CSRF_HEADER_NAME, csrfToken);

    return request;
  },

  onResponse({ request, response }) {
    // A 401 anywhere else means the session died behind our back (expired,
    // signed out in another tab, revoked by a demotion). Dropping the cached
    // identity makes `RequireAuth` redirect on the next render, so no screen
    // keeps rendering as if somebody were signed in.
    //
    // `/auth/*` is excluded on purpose: a rejected login must not be read as
    // "your session ended", which would fight the login screen for control of
    // the route.
    if (response.status === 401 && !new URL(request.url).pathname.startsWith("/auth/")) {
      queryClient.setQueryData(["auth", "me"], null);
    }

    return undefined;
  },
});
