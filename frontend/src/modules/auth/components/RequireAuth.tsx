// Guard for authenticated routes (step-0.1.md §6.2, ui-spec.md §6.3). Owns
// the pending spinner and the retryable error state so no shell flashes
// before the user is known, and is the only component that redirects to
// /signin on an expiry (D21, D27).
import type { ReactNode } from "react";
import { Navigate, type Location, useLocation } from "react-router";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import { useTranslation } from "react-i18next";

import { useCurrentUser } from "../hooks/useCurrentUser";

export interface AuthRedirectState {
  from?: Location;
  reason?: "sessionExpired";
}

function CenteredViewport({ children }: { children: ReactNode }) {
  return (
    <Box
      sx={{
        minHeight: "100dvh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {children}
    </Box>
  );
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { t } = useTranslation("common");
  const location = useLocation();
  const { user, sessionExpired, isPending, isError, refetch } = useCurrentUser();

  if (isPending) {
    return (
      <CenteredViewport>
        <CircularProgress aria-label={t("app.loading")} />
      </CenteredViewport>
    );
  }

  if (isError) {
    return (
      <CenteredViewport>
        <Stack spacing={2} sx={{ alignItems: "center", maxWidth: 480, px: 2 }}>
          <Alert severity="error">{t("errors.network")}</Alert>
          <Button variant="outlined" onClick={refetch}>
            {t("actions.retry")}
          </Button>
        </Stack>
      </CenteredViewport>
    );
  }

  if (!user) {
    const state: AuthRedirectState = sessionExpired ? { from: location, reason: "sessionExpired" } : { from: location };
    return <Navigate to="/signin" replace state={state} />;
  }

  return <>{children}</>;
}
