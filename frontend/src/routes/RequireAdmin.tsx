import { Navigate, Outlet } from "react-router";

import { useAuth } from "../hooks/useAuth";
import { GuardSpinner } from "./RequireAuth";

/**
 * Layout route gating the `/admin` subtree.
 *
 * SECURITY: this guard is **UX only**. It hides admin screens from non-admins;
 * it does not protect any data, because anyone can edit the SPA bundle in their
 * own browser. Every admin API endpoint must therefore depend on the backend
 * `current_admin` dependency (`backend/app/api/deps.py`) — that dependency is
 * the real authorisation boundary, and no admin route may rely on this
 * component for enforcement.
 *
 * Nested inside `RequireAuth`, so an unauthenticated visitor is already gone by
 * the time this renders. Non-admins go to `/` rather than a 403 page: a
 * dedicated error screen would only advertise the existence of the area.
 */
export function RequireAdmin() {
  const { user, isLoading } = useAuth();

  // The `["auth", "me"]` query is shared with RequireAuth and therefore cached
  // by now; the branch exists for a direct render of a guarded child (e.g. a
  // hard reload of /admin) rather than for a second visible spinner.
  if (isLoading) {
    return <GuardSpinner />;
  }

  if (user?.role !== "admin") {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
