import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import { useTranslation } from "react-i18next";
import { Navigate, Outlet, useLocation } from "react-router";

import { useAuth } from "../hooks/useAuth";

/**
 * Loading state shared by every guard: rendered *instead of* the guarded
 * subtree while the identity of the visitor is still unknown, so a signed-in
 * user never sees a flash of the login screen.
 *
 * The guards sit inside `AppLayout`, so this centres in the content area under
 * the AppBar — hence `60vh` rather than a full-viewport overlay.
 */
export function GuardSpinner() {
  const { t } = useTranslation();

  return (
    <Box
      role="status"
      aria-label={t("common.loading")}
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "60vh",
      }}
    >
      <CircularProgress size={48} />
    </Box>
  );
}

/**
 * Layout route gating everything that needs a signed-in user.
 *
 * The intended destination travels in router state rather than the URL, so the
 * login screen can return the user to it without any open-redirect handling.
 *
 * `isLoading` (as opposed to `isFetching`) is true only for the first fetch
 * with no cached data: a background revalidation of `["auth", "me"]` keeps
 * rendering the children instead of replacing them with the spinner.
 */
export function RequireAuth() {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <GuardSpinner />;
  }

  if (user === null) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
