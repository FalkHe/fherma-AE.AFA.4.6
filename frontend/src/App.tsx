import { Navigate, Route, Routes } from "react-router";

import { AdminLayout } from "./components/AdminLayout";
import { AppLayout } from "./components/AppLayout";
import { AdminBacklogRoute } from "./routes/admin/AdminBacklogRoute";
import { AdminModelReviewRoute } from "./routes/admin/AdminModelReviewRoute";
import { CatalogueModelRoute } from "./routes/CatalogueModelRoute";
import { CatalogueRoute } from "./routes/CatalogueRoute";
import { ConsultationChatRoute } from "./routes/ConsultationChatRoute";
import { ConsultationsRoute } from "./routes/ConsultationsRoute";
import { LoginRoute } from "./routes/LoginRoute";
import { RegisterRoute } from "./routes/RegisterRoute";
import { RequireAdmin } from "./routes/RequireAdmin";
import { RequireAuth } from "./routes/RequireAuth";

/**
 * Route table (React Router v7, declarative mode — the package is
 * `react-router`, not `react-router-dom`).
 *
 * A single `AppLayout` wraps everything, including the public auth pages, so
 * the AppBar and theme toggle never disappear; `AppLayout` decides for itself
 * whether to show the nav and account block. The guards are layout routes, so
 * every screen nested under them inherits the loading spinner and the redirect
 * without repeating either.
 *
 * `/consultations` is the authenticated home; the index route is a plain
 * redirect so the list has exactly one canonical URL and the login flow's
 * `navigate(from ?? "/")` keeps working unchanged.
 */
export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="login" element={<LoginRoute />} />
        <Route path="register" element={<RegisterRoute />} />
        <Route element={<RequireAuth />}>
          <Route index element={<Navigate to="/consultations" replace />} />
          <Route path="consultations">
            <Route index element={<ConsultationsRoute />} />
            <Route path=":chatId" element={<ConsultationChatRoute />} />
          </Route>
          <Route path="catalogue">
            <Route index element={<CatalogueRoute />} />
            <Route path=":motorbikeId" element={<CatalogueModelRoute />} />
          </Route>
          <Route element={<RequireAdmin />}>
            <Route path="admin" element={<AdminLayout />}>
              <Route index element={<AdminBacklogRoute />} />
              <Route
                path="models/:motorbikeId"
                element={<AdminModelReviewRoute />}
              />
            </Route>
          </Route>
        </Route>
      </Route>
    </Routes>
  );
}
