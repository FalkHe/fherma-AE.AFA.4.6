// Register creates the user and signs them in (§5.3, step-0.1.md §6.4 OQ-1),
// so success lands on `/` directly — never a detour via `/signin`.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import { api } from "../../../core/api/client";
import { unwrap, type ApiFailure } from "../../../core/api/errors";
import type { Credentials } from "./useSignIn";
import type { CurrentUser, CurrentUserState } from "./useCurrentUser";

export function useSignUp() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  return useMutation<CurrentUser, ApiFailure, Credentials>({
    mutationFn: (credentials) => unwrap(api.POST("/api/v1/auth/register", { body: credentials })),
    onSuccess: (user) => {
      queryClient.setQueryData<CurrentUserState>(["currentUser"], { user, sessionExpired: false });
      navigate("/", { replace: true });
    },
  });
}
