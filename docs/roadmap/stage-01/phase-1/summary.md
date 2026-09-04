# Phase 1 — Accounts and access

**Goal:** A person can register, sign in, and be made an admin.

## Delivered

- `users` + `sessions` tables in one migration; Argon2 hashing, sessions as
  opaque tokens stored only as hashes.
- Auth API — register / login / logout / who-am-I, plain JSON with fixed error
  sentences; the UI branches on status code, never on message text.
- Cookie session with "remember me" — HttpOnly session cookie (24 h, or 30 days)
  plus a CSRF cookie checked on every authenticated write.
- Two roles (user/admin), enforced server-side by reusable guards every later
  route inherits; the role is re-read per request, so a promotion applies on the
  next page load without re-login.
- Login and registration screens — translated MUI forms, client-side validation,
  in-button spinners, password-manager and screen-reader support.
- Route guards and the admin shell — no-flash loading, deep-link-preserving
  redirect to login, `/admin` with a "Backlog — coming soon" empty state,
  role-conditional nav, account menu with sign-out.
- Client wiring — regenerated typed client; shared middleware attaches the CSRF
  header and turns an expired session into a login redirect, so no screen
  handles those cases itself.
- Admin bootstrap — `app users set-role` / `app users reset-password` (password
  prompted, never an argument). This is how the first admin is created.

## Non-obvious decisions

- Two parallel tracks built against a frozen written contract, not against code,
  with a single sync point. Cost: "redirect signed-in users away from /login"
  had to wait for the wiring step, since with the stub it made the auth pages
  unreachable in development.
- Fixed session expiry, no sliding renewal — simpler and auditable, at the price
  of occasional forced re-login.
- Cookies, not bearer tokens — required for the Phase 2 live-updates channel to
  authenticate at all; not reversible later.
- Sessions revoked on password reset and on admin→user demotion only; promotion
  deliberately does not sign the user out.
- Registration does not sign you in; the client chains a login call — keeps the
  endpoint single-purpose while still giving one-step onboarding.
- Login checks credentials rather than validating their format (adjusted
  post-phase) — a too-short password previously surfaced as a server error
  instead of "invalid credentials".
- No self-service password reset, hence a confirm-password field — a typo in a
  masked field would otherwise lock the account permanently; recovery is
  admin-only via CLI.
- Uniform "invalid username or password" plus constant-time checking for unknown
  users — prevents probing which accounts exist.
- Usernames folded to lowercase rather than rejected — case-insensitive
  uniqueness with no extra machinery.
- Browser-side guards are UX only; every admin endpoint enforces the role.

## Not delivered / deferred

- Live role propagation without a page reload — waits for the Phase 2 SSE
  channel.
- Admin backlog content — shell only; filled in Phase 2, which also dropped the
  planned second "Review" tab in favour of a drill-down page.
- Rate limiting, password-strength policy, drawer navigation, session-management
  screens — dropped from project scope.
