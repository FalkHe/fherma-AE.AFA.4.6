// The signed-in user lives in TanStack Query, keyed ["currentUser"]
// (step-0.1.md §6.2, D27). A 401 is an expected state, not an error: it
// resolves to no user, and `sessionExpired` records whether the server said
// SESSION_EXPIRED (a cookie was sent and resolved to nothing) or
// NOT_AUTHENTICATED (no cookie). There is no client-side memory of having
// been signed in — the code is read fresh off every response.
import { useQuery } from "@tanstack/react-query";

import { api } from "../../../core/api/client";
import { unwrap, type ApiFailure } from "../../../core/api/errors";
import type { components } from "../../../api/schema";

export type CurrentUser = components["schemas"]["UserRead"];

export interface CurrentUserState {
  user: CurrentUser | null;
  sessionExpired: boolean;
}

async function fetchCurrentUser(): Promise<CurrentUserState> {
  try {
    const user = await unwrap(api.GET("/api/v1/users/me", {}));
    return { user, sessionExpired: false };
  } catch (error) {
    const failure = error as ApiFailure;
    if (failure.status === 401) {
      return { user: null, sessionExpired: failure.code === "SESSION_EXPIRED" };
    }
    throw failure;
  }
}

export function useCurrentUser() {
  const query = useQuery({
    queryKey: ["currentUser"],
    queryFn: fetchCurrentUser,
  });

  return {
    user: query.data?.user ?? null,
    sessionExpired: query.data?.sessionExpired ?? false,
    isPending: query.isPending,
    isError: query.isError,
    refetch: () => {
      void query.refetch();
    },
  };
}
