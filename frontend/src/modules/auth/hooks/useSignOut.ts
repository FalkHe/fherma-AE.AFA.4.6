// One owner per redirect to /signin (D21). A 401 on this request is treated
// exactly like success inside `mutationFn` itself — the session is already
// gone, which is what the user asked for — so exactly one `onSuccess`
// handler runs for both cases: navigate first, then clear the CSRF token,
// then write the cache, in that order (step-0.1.md §6.2). 403 / 5xx / an
// unmapped code / NETWORK are left to throw and surface as `mutation.error`,
// which HomeRoute renders as `auth:signOut.error`.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import { api, clearCsrfToken } from "../../../core/api/client";
import { unwrap, type ApiFailure } from "../../../core/api/errors";
import type { CurrentUserState } from "./useCurrentUser";

export function useSignOut() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  return useMutation<void, ApiFailure, void>({
    mutationFn: async () => {
      try {
        await unwrap(api.POST("/api/v1/auth/sign-out", {}));
      } catch (error) {
        const failure = error as ApiFailure;
        if (failure.status === 401) {
          return;
        }
        throw failure;
      }
    },
    onSuccess: () => {
      navigate("/signin", { replace: true });
      clearCsrfToken();
      queryClient.setQueryData<CurrentUserState>(["currentUser"], { user: null, sessionExpired: false });
      // `navigate()` above runs through a React transition (BrowserRouter's
      // default), while the cache write just above is not deferrable the
      // same way — it can commit first, so the still-mounted RequireAuth
      // briefly sees the page being signed out of with `user: null` and
      // fires its own redirect to /signin, carrying that page as
      // `state.from`. That effect always runs after this callback returns,
      // so it cannot be beaten by writing state here — only overwritten
      // afterwards. Queuing this last, empty-state replace for the next
      // macrotask lets that effect (and React's dev-only double-invoke of
      // it) settle first, then wins: the remembered address does not
      // outlive the sign-in that consumes it.
      setTimeout(() => {
        navigate("/signin", { replace: true, state: null });
      }, 0);
    },
  });
}
