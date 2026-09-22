// The route table, nothing else (step-0.1.md §6.2). No provider, no router:
// main.tsx supplies BrowserRouter, a test supplies MemoryRouter (criterion 46).
// The signed-in guard is declared once, as a pathless layout route wrapping
// every signed-in address (AC1) — it sits outside AppShell so no header
// flashes while the session read is pending or errored (sprint 007/04 WI1).
import { Navigate, Outlet, Route, Routes } from "react-router";

import { AccountMenu } from "./modules/auth/components/AccountMenu";
import { RequireAnonymous } from "./modules/auth/components/RequireAnonymous";
import { RequireAuth } from "./modules/auth/components/RequireAuth";
import { SignInRoute } from "./modules/auth/routes/SignInRoute";
import { SignUpRoute } from "./modules/auth/routes/SignUpRoute";
import { AppShell } from "./core/layout/AppShell";
import { DashboardRoute } from "./modules/playthrough/routes/DashboardRoute";
import { RunRoute } from "./modules/playthrough/routes/RunRoute";

export default function App() {
  return (
    <Routes>
      <Route
        element={
          <RequireAuth>
            <AppShell action={<AccountMenu />}>
              <Outlet />
            </AppShell>
          </RequireAuth>
        }
      >
        <Route path="/" element={<DashboardRoute />} />
        <Route path="/runs/:runId" element={<RunRoute />} />
      </Route>
      <Route element={<RequireAnonymous><Outlet /></RequireAnonymous>}>
        <Route path="/signin" element={<SignInRoute />} />
        <Route path="/signup" element={<SignUpRoute />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
