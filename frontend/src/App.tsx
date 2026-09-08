// The route table, nothing else (step-0.1.md §6.2). No provider, no router:
// main.tsx supplies BrowserRouter, a test supplies MemoryRouter (criterion 46).
import { Navigate, Route, Routes } from "react-router";

import { RequireAnonymous } from "./modules/auth/components/RequireAnonymous";
import { RequireAuth } from "./modules/auth/components/RequireAuth";
import { SignInRoute } from "./modules/auth/routes/SignInRoute";
import { SignUpRoute } from "./modules/auth/routes/SignUpRoute";
import { HomeRoute } from "./modules/home/routes/HomeRoute";

export default function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <RequireAuth>
            <HomeRoute />
          </RequireAuth>
        }
      />
      <Route
        path="/signin"
        element={
          <RequireAnonymous>
            <SignInRoute />
          </RequireAnonymous>
        }
      />
      <Route
        path="/signup"
        element={
          <RequireAnonymous>
            <SignUpRoute />
          </RequireAnonymous>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
