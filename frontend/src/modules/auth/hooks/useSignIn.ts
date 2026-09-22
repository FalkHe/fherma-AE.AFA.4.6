import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router";

import { api } from "../../../core/api/client";
import { unwrap, type ApiFailure } from "../../../core/api/errors";
import type { AuthRedirectState } from "../components/RequireAuth";
import type { CurrentUser, CurrentUserState } from "./useCurrentUser";

export interface Credentials {
  username: string;
  password: string;
}

export function useSignIn() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();

  return useMutation<CurrentUser, ApiFailure, Credentials>({
    mutationFn: (credentials) => unwrap(api.POST("/api/v1/auth/sign-in", { body: credentials })),
    onSuccess: (user) => {
      const state = location.state as AuthRedirectState | null;
      navigate(state?.from ?? "/", { replace: true });
      queryClient.setQueryData<CurrentUserState>(["currentUser"], { user, sessionExpired: false });
    },
  });
}
