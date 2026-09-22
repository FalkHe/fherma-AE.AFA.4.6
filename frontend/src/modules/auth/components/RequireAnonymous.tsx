// Guard for /signin and /signup (step-0.1.md §6.2, ui-spec.md §6.4). Shares
// the same pending spinner as RequireAuth so both guards agree on what
// "unknown" looks like, and sends an authenticated visitor back to / with no
// message.
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import { useTranslation } from "react-i18next";

import { useCurrentUser } from "../hooks/useCurrentUser";
import type { AuthRedirectState } from "./RequireAuth";

export function RequireAnonymous({ children }: { children: ReactNode }) {
  const { t } = useTranslation("common");
  const { user, isPending } = useCurrentUser();
  const location = useLocation();

  if (isPending) {
    return (
      <Box sx={{ minHeight: "100dvh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <CircularProgress aria-label={t("app.loading")} />
      </Box>
    );
  }

  if (user) {
    const state = location.state as AuthRedirectState | null;
    return <Navigate to={state?.from ?? "/"} replace />;
  }

  return <>{children}</>;
}
