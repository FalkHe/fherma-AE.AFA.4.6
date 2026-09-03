import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient } from "../api/client";
import type { components } from "../api/schema";

/**
 * Session handling for the whole SPA: one cached identity query plus the three
 * mutations that change it.
 *
 * The identity lives in the query cache under `["auth", "me"]` rather than in a
 * context of its own — it is server state, it can go stale behind our back
 * (expiry, sign-out in another tab, a role change), and TanStack Query already
 * owns exactly that problem. `api/client.ts` writes `null` into the same key
 * when any other request answers 401, which is what makes an expired session
 * surface as a redirect instead of a broken screen.
 */

/** The `["auth", "me"]` cache key — also written to by the client middleware. */
const AUTH_ME_QUERY_KEY = ["auth", "me"] as const;

/** `UserResponse` from the pinned auth API contract. */
export type AuthUser = components["schemas"]["UserResponse"];

/** Request body of `POST /auth/login`. */
export type LoginInput = components["schemas"]["LoginRequest"];

/** Request body of `POST /auth/register`. */
export type RegisterInput = components["schemas"]["RegisterRequest"];

/**
 * A failed `/auth/*` call, carrying the status code the screens branch on.
 *
 * The backend's `detail` sentences are English prose meant for developers; the
 * UI decides its own message from the status code alone (401/403/409/422), as
 * pinned in shared-knowledge. `validationFields` carries the field names of a
 * 422 body so a validation error that slipped past the client checks can be
 * shown on the field it belongs to.
 */
export class AuthError extends Error {
  readonly status: number;
  readonly validationFields: readonly string[];

  constructor(status: number, validationFields: readonly string[] = []) {
    super(`Auth request failed with status ${status}`);
    this.name = "AuthError";
    this.status = status;
    this.validationFields = validationFields;
  }
}

type ValidationErrorBody = components["schemas"]["HTTPValidationError"];

/**
 * Field names out of a FastAPI 422 body: `loc` is `["body", "<field>"]`, so the
 * last segment is the field — anything else (a whole-body error) yields nothing
 * and the caller falls back to its general error slot.
 */
function validationFieldsOf(body: ValidationErrorBody | undefined): readonly string[] {
  return (body?.detail ?? []).flatMap((item) => {
    const field = item.loc.at(-1);

    return typeof field === "string" && field !== "body" ? [field] : [];
  });
}

function authError(status: number, body?: ValidationErrorBody): AuthError {
  return new AuthError(status, status === 422 ? validationFieldsOf(body) : []);
}

/**
 * `GET /auth/me`, with 401 resolving to "nobody is signed in" rather than to an
 * error: being anonymous is a normal state of this application, not a failure,
 * and modelling it as one would leave every guard inspecting error objects.
 */
async function fetchCurrentUser(): Promise<AuthUser | null> {
  const { data, response } = await apiClient.GET("/auth/me");

  if (response.status === 401) {
    return null;
  }

  if (!response.ok || data === undefined) {
    throw authError(response.status);
  }

  return data;
}

/** `POST /auth/login` — the only call that issues the session and CSRF cookies. */
async function login(body: LoginInput): Promise<AuthUser> {
  const { data, error, response } = await apiClient.POST("/auth/login", { body });

  if (!response.ok || data === undefined) {
    throw authError(response.status, error);
  }

  return data;
}

/**
 * Signed-in user, shared by the guards and the layout.
 *
 * `isLoading` is deliberately the first-fetch flag, not `isFetching`: guards
 * render this instead of their children, so surfacing background revalidations
 * here would blank a working page every time the identity is refreshed.
 */
export function useAuth(): {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
} {
  const { data, isLoading } = useQuery({
    queryKey: AUTH_ME_QUERY_KEY,
    queryFn: fetchCurrentUser,
    // A 401 is an answer, not a hiccup — retrying it only delays the redirect.
    retry: false,
    staleTime: 5 * 60_000,
  });

  const user = data ?? null;

  return { user, isLoading, isAuthenticated: user !== null };
}

/**
 * Signs in. The response body is written straight into the identity cache, so
 * the redirect that follows renders from data already in hand instead of
 * waiting on a refetch of something the server just told us.
 */
export function useLogin(): UseMutationResult<AuthUser, Error, LoginInput> {
  const queryClient = useQueryClient();

  return useMutation<AuthUser, Error, LoginInput>({
    mutationFn: login,
    onSuccess: (user) => {
      queryClient.setQueryData(AUTH_ME_QUERY_KEY, user);
    },
  });
}

/**
 * Registers, then signs the new account in with the same credentials.
 *
 * The chained login lives here rather than in the screen because `/auth/register`
 * deliberately creates no session: keeping both calls inside one mutation means
 * the UI still has a single pending state and a single failure path, and it is
 * why this resolves to the authenticated user rather than the created one.
 */
export function useRegister(): UseMutationResult<AuthUser, Error, RegisterInput> {
  const queryClient = useQueryClient();

  return useMutation<AuthUser, Error, RegisterInput>({
    mutationFn: async ({ username, password }) => {
      const { error, response } = await apiClient.POST("/auth/register", {
        body: { username, password },
      });

      if (!response.ok) {
        throw authError(response.status, error);
      }

      return login({ username, password, rememberMe: false });
    },
    onSuccess: (user) => {
      queryClient.setQueryData(AUTH_ME_QUERY_KEY, user);
    },
  });
}

/**
 * Signs out.
 *
 * A 401 counts as success: the session is gone either way, and reporting an
 * error for "you were already signed out" would leave the user stuck on a page
 * they can no longer use. Anything else (a 403 from a stale CSRF cookie, a 5xx)
 * is a real failure and keeps the cache intact, so the caller can leave the user
 * where they are.
 *
 * Clearing the cache belongs here — every cached page is per-user data. The
 * navigation that follows belongs to the caller, which is the component that
 * knows where the user was.
 */
export function useLogout(): UseMutationResult<void, Error, void> {
  const queryClient = useQueryClient();

  return useMutation<void, Error, void>({
    mutationFn: async () => {
      const { response } = await apiClient.POST("/auth/logout");

      if (!response.ok && response.status !== 401) {
        throw authError(response.status);
      }
    },
    onSuccess: () => {
      queryClient.clear();
    },
  });
}
