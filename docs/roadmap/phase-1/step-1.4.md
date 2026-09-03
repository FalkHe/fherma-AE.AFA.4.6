---
phase: 1
step: "1.4"
title: Route guards & admin shell, UI-only
summary: RequireAuth/RequireAdmin guards with the spinner pattern, the nested /admin subtree with the empty admin shell, and role-conditional navigation plus sign-out in the app bar — all against the stub useAuth.
effort: 3
dependencies: ["1.2"]
agent: frontend-dev
track: frontend
---

# Step 1.4 — Route guards & admin shell, UI-only

**Effort: 3** — two small guard components, one layout, one empty-state page,
and AppBar additions; establishes the guard pattern every later admin feature
reuses.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) (route table, guard behaviour,
stub rule) and [`ui-spec.md`](ui-spec.md) §3, §4, §5, §6, §7. Runs in
parallel with backend steps — do not touch `backend/`, no API calls.

## Files

- Create `frontend/src/routes/RequireAuth.tsx`,
  `frontend/src/routes/RequireAdmin.tsx`
- Create `frontend/src/components/AdminLayout.tsx`,
  `frontend/src/routes/admin/AdminHomeRoute.tsx`
- Modify `frontend/src/App.tsx` — the **full pinned route table** from
  shared-knowledge (one `AppLayout` wrapping everything; `login`/`register`
  public; `RequireAuth` → home; `RequireAuth` → `RequireAdmin` →
  `AdminLayout` → `AdminHomeRoute`)
- Modify `frontend/src/components/AppLayout.tsx` — nav + account menu per
  ui-spec §4 (conditional Admin item, username display, sign-out calling the
  stub `useLogout`)
- Modify `frontend/src/locales/en/translation.json` — merge `nav.admin`,
  `account.*`, `admin.*` keys from ui-spec §6

## Implementation outline

- **Guards** exactly per shared-knowledge + ui-spec §3: while
  `useAuth().isLoading`, render the centered `CircularProgress`
  (`role="status"`, translated `aria-label`, `minHeight: "60vh"`) — never
  flash a redirect. `RequireAuth`: unauthenticated →
  `<Navigate to="/login" state={{ from: location }} replace />`.
  `RequireAdmin`: `role !== "admin"` → `<Navigate to="/" replace />`.
  Background refetches with data present must not re-show the spinner. This
  spinner-then-outlet shape is **the pattern all later guarded routes
  inherit** — keep it in the guards, not in pages.
- **AdminLayout + AdminHomeRoute** per ui-spec §5: h4 title, secondary
  `Tabs` bar with the single Backlog tab (value derived from
  `useLocation().pathname`; no disabled placeholder tabs), `<Outlet />`;
  the empty state per the reusable pattern ("Backlog — coming soon").
- **AppLayout** per ui-spec §4: inline AppBar nav (`Home` always for
  signed-in users, `Admin` only when `useAuth().user?.role === "admin"`),
  account menu (username trigger, signed-in-as item, sign-out item wired to
  the stub `useLogout`), account block rendered only when `user` exists.
- The committed stub keeps `role: "user"` (see verification).
- i18n for every new string; no hardcoded text.

## Out of scope (later steps)

- Real `/auth/me` query, real logout, cache clearing, 401 handling →
  step 1.6.
- Live role propagation after a role change — a reload is acceptable until
  the Phase-2 SSE channel exists; do not build it.

## Verification

- `pnpm tsc --noEmit` passes.
- With the committed stub (`role: "user"`): app shell renders at `/`; no
  Admin nav item; manual navigation to `/admin` redirects to `/`.
- Temporarily editing `STUB_USER.role` to `"admin"` in the dev server: the
  Admin nav item appears; `/admin` shows the tabbed shell with the empty
  state. **Revert before commit** — verify `git diff` shows `role: "user"`.
- Account menu shows the stub username; sign-out is clickable (no-op);
  on `xs` viewport the trigger degrades to icon-only.
- Theme toggle still works on every screen, light and dark.

## Risks / notes

- Frontend guards are **UX only** — put a comment in `RequireAdmin.tsx`
  stating that every admin API endpoint must use the backend `current_admin`
  dependency, so Phase-2 agents don't rely on the SPA guard.
- Under the stub, `isLoading` is always `false`, so the spinner branch is
  unexercised until 1.6 — implement it anyway, exactly per spec.
