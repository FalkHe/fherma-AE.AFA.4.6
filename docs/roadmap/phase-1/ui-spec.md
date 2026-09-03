# Phase 1 — UI Specification (binding for frontend steps)

Produced by the ui-ux-designer; binding for steps 1.2, 1.4, and 1.6. Read
[`shared-knowledge.md`](shared-knowledge.md) first — it pins file names, the
route table, hook shapes, and the API contract these specs assume.

Shared conventions for every spec below:

- MUI v6/v7, Material Design 2 look, stock components only. Theme modes work
  via `colorSchemes`; never hardcode colors — use palette tokens
  (`text.secondary`, `error`, `divider`, …).
- All strings via react-i18next `t()` — full key list in §6. No hardcoded
  text, including `aria-label`s.
- Plain controlled inputs (`useState` per field). No React Hook Form/Zod.
- Mutations via TanStack Query `useMutation` over the typed `openapi-fetch`
  client (stubbed until step 1.6).

---

## 1. LoginRoute — `/login`

Public route inside `AppLayout` (AppBar + theme toggle stay visible; the
account menu does not render because it requires `useAuth().user` — see §4).
The intended destination arrives via router state (`location.state.from`, a
`Location`), **not** the URL — avoids open-redirect handling and survives the
SPA redirect from `RequireAuth`. In step 1.6 (not before): if `useAuth`
reports an authenticated user, immediately `<Navigate to="/" replace />`.

**Layout:**

```
┌────────────── AppBar (existing) ──────────────┐
│                                               │
│        ┌────── Paper, maxWidth 400 ─────┐     │
│        │  Sign in                (h5)   │     │
│        │  [Alert: error]  (conditional) │     │
│        │  [ Username            ]       │     │
│        │  [ Password            ]       │     │
│        │  [x] Remember me               │     │
│        │  [      SIGN IN (full) ]       │     │
│        │  No account? Create one (link) │     │
│        └────────────────────────────────┘     │
```

- Wrapper: `<Box sx={{ display: "flex", justifyContent: "center", pt: { xs: 2, sm: 8 } }}>`;
  card is `<Paper component="form" onSubmit={...} sx={{ p: 4, width: "100%", maxWidth: 400 }}>`
  (on xs the `p: 4` + full width is fine; no separate mobile layout).
- Inside the Paper: `<Stack spacing={3}>`:
  1. `<Typography variant="h5" component="h1">` — `auth.login.title`.
  2. Conditional `<Alert severity="error">` (MUI's default `role="alert"`
     announces it) — see states below.
  3. `<TextField label={t("auth.fields.username")} name="username" autoComplete="username" autoFocus required fullWidth />`.
  4. `<TextField label={t("auth.fields.password")} name="password" type="password" autoComplete="current-password" required fullWidth />`.
  5. `<FormControlLabel control={<Checkbox />} label={t("auth.login.rememberMe")} />` —
     default **unchecked**.
  6. `<Button type="submit" variant="contained" fullWidth disabled={isPending} startIcon={isPending ? <CircularProgress size={20} color="inherit" /> : undefined}>` —
     `auth.login.submit`.
  7. `<Typography variant="body2">` with `auth.login.noAccount` +
     `<Link component={RouterLink} to="/register">` `auth.login.registerLink`.

**States:**

| State | Rendering |
|---|---|
| Idle | Form as above, Alert absent. |
| Pending | Submit button disabled + `CircularProgress size={20}` startIcon; both TextFields and the Checkbox get `disabled`. This is the required progress indicator. |
| Error — 401 | Alert with `auth.errors.invalidCredentials` (one generic message; never distinguish unknown user vs wrong password). Password field cleared; focus returned to username. |
| Error — network/5xx | Alert with `auth.errors.serverError`. Form values preserved. |
| Success | Invalidate/refetch the `["auth","me"]` query, then `navigate(from ?? "/", { replace: true })`. No success toast — the destination render is the feedback. |

Client-side validation: only `required` (browser-level via the `required`
prop). No length checks on login — the server decides.

---

## 2. RegisterRoute — `/register`

Public route inside `AppLayout`; same step-1.6 authenticated-redirect rule as
§1.

**Decisions:**

- **Confirm password: yes.** There is no self-service password reset, so a
  typo in a masked field would lock the account; the confirm field is the
  only guard.
- **After success: auto-login + redirect to `/`.** `POST /auth/register`,
  then immediately `POST /auth/login` with the same credentials
  (`rememberMe: false`) — one fewer screen, no "please log in again"
  friction.

**Layout:** identical shell to §1 (centered `Paper` maxWidth 400,
`Stack spacing={3}`):

1. `<Typography variant="h5" component="h1">` — `auth.register.title`.
2. Conditional `<Alert severity="error">` — **general** errors only
   (network/5xx: `auth.errors.serverError`).
3. `<TextField>` username — `autoComplete="username"`, `autoFocus`,
   `required`; `helperText` defaults to `auth.register.usernameHint`,
   switches to the field error when invalid.
4. `<TextField>` password — `type="password"`,
   `autoComplete="new-password"`, `required`; `helperText` defaults to
   `auth.register.passwordHint`.
5. `<TextField>` confirm password — `type="password"`,
   `autoComplete="new-password"`, `required`.
6. Submit `<Button variant="contained" fullWidth>` —
   `auth.register.submit`; same pending pattern as §1.
7. `<Typography variant="body2">` — `auth.register.haveAccount` +
   `<Link component={RouterLink} to="/login">` `auth.register.loginLink`.

**Field-level vs general errors** — field errors set `error` + `helperText`
on the specific `TextField`:

| Cause | Where | Message key |
|---|---|---|
| Client: username charset/length (validate on submit; mirror the pinned backend rule) | username field | `auth.errors.usernameInvalid` |
| Client: password shorter than 8 | password field | `auth.errors.passwordTooShort` |
| Client: confirm ≠ password | confirm field | `auth.errors.passwordMismatch` |
| Server 409 (username taken) | username field | `auth.errors.usernameTaken` |
| Server 422 (slipped past client checks) | map `loc` field name → matching field; unmappable → general Alert | field keys above / `auth.errors.serverError` |
| Network/5xx, or the chained login call fails | general Alert | `auth.errors.serverError` |

Client validation runs only on submit (no blur/keystroke validation — keeps
controlled inputs trivial); the first invalid field receives focus.

**States:** idle / pending (identical to §1: all inputs disabled, spinner in
button) / field error / general error / success (auto-login →
`navigate("/", { replace: true })`).

---

## 3. Guard loading state (`RequireAuth`, reused by `RequireAdmin`)

While the `GET /auth/me` query is in `isLoading` (first fetch, no cached
data), the guard renders **instead of** its children — never a redirect
flash:

```tsx
<Box
  role="status"
  aria-label={t("common.loading")}
  sx={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "60vh" }}
>
  <CircularProgress size={48} />
</Box>
```

- The guards sit inside `AppLayout` (see the pinned route table), so the
  spinner centers in the content area under the AppBar — `minHeight: "60vh"`,
  not full viewport.
- Once resolved: authenticated → render `<Outlet />`; unauthenticated →
  `<Navigate to="/login" replace state={{ from: location }} />`.
- `RequireAdmin` reuses the same query and spinner (the query is cached, so
  in practice it never shows twice); role ≠ `admin` →
  `<Navigate to="/" replace />`.
- Background refetches (`isFetching` with data present) must **not** re-show
  the spinner — keep rendering children.

---

## 4. AppLayout additions (nav + account)

Modify the existing `frontend/src/components/AppLayout.tsx`.
**Decision: AppBar inline nav, no Drawer** — two links (Home, Admin) do not
justify drawer plumbing, and both fit on a phone toolbar.

```
┌───────────────────────────────────────────────────────────────┐
│ Motorcycle Buying Advisor   [Home] [Admin]   ◐  (👤 falk ▾)   │
└───────────────────────────────────────────────────────────────┘
```

Toolbar order (left → right):

1. Existing title `Typography` (`flexGrow: 1`, links to `/`).
2. Nav in `<Box sx={{ display: "flex", gap: 1, mr: 1 }}>`:
   `<Button color="inherit" component={RouterLink} to="/">` `nav.home`;
   `<Button color="inherit" component={RouterLink} to="/admin">` `nav.admin`
   — **rendered only when `useAuth().user?.role === "admin"`**. No
   active-state styling needed in Phase 1.
3. Existing `<ThemeModeToggle />`.
4. **Account menu** (rendered only when `useAuth().user` exists — hence
   `/login` can share this layout):
   - Trigger:
     `<Button color="inherit" startIcon={<AccountCircle />} endIcon={<ArrowDropDown />} aria-label={t("account.menuLabel")}>`
     showing the username; on `xs` hide the text
     (`<Box component="span" sx={{ display: { xs: "none", sm: "inline" } }}>{username}</Box>`)
     so it degrades to icon-only.
   - `<Menu>` anchored to it:
     - `<MenuItem disabled>` — `account.signedInAs` with `{{username}}`
       interpolation (shows the name on mobile where the trigger hides it).
     - `<Divider />`
     - `<MenuItem onClick={signOut}>` with
       `<ListItemIcon><Logout fontSize="small" /></ListItemIcon>` —
       `account.signOut`.
   - Sign-out flow: `POST /auth/logout` (mutation); while pending the
     MenuItem is `disabled`; on settle (success **or** 401) clear the
     TanStack Query cache (`queryClient.clear()`) and
     `navigate("/login", { replace: true })`. On other errors: close the
     menu, no navigation.

Icons: `AccountCircle`, `ArrowDropDown`, `Logout` — follow the icon
convention already in place for `ThemeModeToggle`.

**States:** render the nav + account block only when `user` exists; while
`/auth/me` is loading inside the layout, render nothing in that slot (no
skeleton — the guards already gate the interesting routes).

---

## 5. AdminLayout + AdminHomeRoute — `/admin`

**Decision: secondary `Tabs` bar, not a sidebar** — admin has exactly two
planned sections (Backlog, Review), tabs are zero responsive work, and they
nest cleanly inside the existing content container.

**AdminLayout** (renders in `AppLayout`'s Outlet):

```
┌ Content area (from AppLayout) ─────────────┐
│ Admin                                (h4)  │
│ ┌ Tabs ────────────────────────────────┐   │
│ │ [ Backlog ]                          │   │
│ └──────────────────────── divider ─────┘   │
│ <Outlet />                                 │
└────────────────────────────────────────────┘
```

- `<Typography variant="h4" component="h1" gutterBottom>` — `admin.title`.
- `<Tabs value={tabValue} sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }} variant="scrollable" allowScrollButtonsMobile>`
  where `tabValue` derives from `useLocation().pathname` (`/admin` →
  `"backlog"`); Phase 2 adds `/admin/review`.
- One tab now:
  `<Tab value="backlog" label={t("admin.tabs.backlog")} component={RouterLink} to="/admin" />`.
  Do **not** render a disabled Review tab — dead controls are noise.
- `<Outlet />` below.

**AdminHomeRoute** (index route) — the **reusable empty-state pattern** (this
exact structure will be reused for empty consultation lists etc.):

```tsx
<Stack spacing={1} alignItems="center" sx={{ py: 8, textAlign: "center", color: "text.secondary" }}>
  <PendingActions sx={{ fontSize: 56 }} />
  <Typography variant="h6" component="h2" color="text.primary">
    {t("admin.backlog.emptyTitle")}
  </Typography>
  <Typography variant="body2" sx={{ maxWidth: 440 }}>
    {t("admin.backlog.emptyBody")}
  </Typography>
</Stack>
```

Pattern rules: centered `Stack`, icon 56px in `text.secondary`, `h6` title,
`body2` body capped at ~440px, optional action `Button` slot last (unused
here).

**States:** no loading/error states — the page makes no API calls in
Phase 1. Guard states (spinner, redirect) are inherited from §3.

---

## 6. i18n keys (merge into `frontend/src/locales/en/translation.json`)

Existing `nav.home` stays; only `nav.admin` is new in that block.

```json
{
  "nav": {
    "home": "Home",
    "admin": "Admin"
  },
  "common": {
    "loading": "Loading"
  },
  "auth": {
    "fields": {
      "username": "Username",
      "password": "Password",
      "confirmPassword": "Confirm password"
    },
    "login": {
      "title": "Sign in",
      "rememberMe": "Remember me",
      "submit": "Sign in",
      "noAccount": "No account yet?",
      "registerLink": "Create one"
    },
    "register": {
      "title": "Create account",
      "usernameHint": "3–32 characters: letters, digits, . _ -",
      "passwordHint": "At least 8 characters",
      "submit": "Create account",
      "haveAccount": "Already have an account?",
      "loginLink": "Sign in"
    },
    "errors": {
      "invalidCredentials": "Invalid username or password.",
      "usernameTaken": "This username is already taken.",
      "usernameInvalid": "Use 3–32 characters: letters, digits, . _ -",
      "passwordTooShort": "Password must be at least 8 characters.",
      "passwordMismatch": "Passwords do not match.",
      "serverError": "Something went wrong. Please try again."
    }
  },
  "account": {
    "menuLabel": "Account",
    "signedInAs": "Signed in as {{username}}",
    "signOut": "Sign out"
  },
  "admin": {
    "title": "Admin",
    "tabs": {
      "backlog": "Backlog"
    },
    "backlog": {
      "emptyTitle": "Backlog — coming soon",
      "emptyBody": "Catalogue-gap reports from consultations will appear here for review in a later release."
    }
  }
}
```

These messages mirror the validation rules pinned in `shared-knowledge.md` —
if those rules ever change, change both.

---

## 7. Accessibility / UX checklist (applies to §1–§5)

- **Autofocus:** username field on both auth pages (`autoFocus` prop); after
  a 401 login error, programmatic focus back to username via ref.
- **Autocomplete:** `username` on both username fields; `current-password`
  (login) vs `new-password` (register + confirm) — enables password-manager
  save/fill.
- **Enter submits:** guaranteed by `Paper component="form"` +
  `Button type="submit"`; never bind key handlers manually.
- **Pending:** disable submit **and** all inputs while the mutation is in
  flight; spinner lives in the button
  (`CircularProgress size={20} color="inherit"`), no full-page overlay.
  Guard against double submit via the `disabled` state, not debouncing.
- **Error announcement:** general errors in `<Alert severity="error">`
  (implicit `role="alert"` → announced on mount); field errors via
  `TextField error + helperText` (MUI wires `aria-describedby`
  automatically).
- **Gate spinner:** `role="status"` + translated `aria-label` (§3) so
  assistive tech doesn't perceive a blank page.
- **Menus:** MUI `Menu` handles focus trap/escape/arrow keys — no extra
  work; ensure the account trigger has the translated `aria-label` for the
  icon-only xs variant.
- **Links vs buttons:** navigation is `Link`/`Button component={RouterLink}`
  (real hrefs, middle-click works); never `onClick` + `navigate` for plain
  navigation.
- **No password reveal toggle, no caps-lock hint, no strength meter** — out
  of scope; strict password policy is explicitly out of scope per
  `docs/architecture.md`.
