---
phase: 1
step: "1.2"
title: Auth screens, UI-only
summary: Login and registration pages as fully styled, i18n'd MUI forms with client-side validation, mounted at public routes, submitting to stub hooks — zero backend required.
effort: 3
dependencies: ["0.4"]
agent: frontend-dev
track: frontend
---

# Step 1.2 — Auth screens, UI-only

**Effort: 3** — two forms and a stub hook; the layout, validation, and state
handling are fully specified, so this is careful assembly, not design.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) (contract; especially the
*Frontend conventions* and *Stub rule* sections) and
[`ui-spec.md`](ui-spec.md) §1, §2, §6, §7 (binding layout/state/i18n/a11y
spec). Runs in parallel with backend step 1.1 — do not touch `backend/`, and
make **no API calls**.

## Files

- Create `frontend/src/routes/LoginRoute.tsx`,
  `frontend/src/routes/RegisterRoute.tsx`
- Create `frontend/src/hooks/useAuth.ts` — the **stub** exactly per the
  shared-knowledge stub rule (`STUB_USER`, `isLoading: false`; async no-op
  `useLogin`/`useRegister`/`useLogout` with the real call signatures)
- Modify `frontend/src/App.tsx` — add `/login` and `/register` as public
  routes **inside** `AppLayout` (see the pinned route table; the `RequireAuth`
  branch is step 1.4's job — leave the existing home route as is for now)
- Modify `frontend/src/locales/en/translation.json` — merge the `common.*`
  and `auth.*` keys from ui-spec §6

## Implementation outline

- Build both screens exactly per ui-spec §1/§2: centered
  `Paper component="form"` maxWidth 400, `Stack spacing={3}`, plain
  controlled inputs, remember-me checkbox (login), confirm-password field
  (register), cross-links between the two pages.
- Client-side validation on submit only, mirroring the pinned rules
  (username: 3–32 chars, `^[a-z0-9_.-]+$` after lowercase-fold — show
  `auth.errors.usernameInvalid`; password ≥ 8 —
  `auth.errors.passwordTooShort`; confirm matches —
  `auth.errors.passwordMismatch`); errors via `TextField error + helperText`;
  first invalid field gets focus.
- The general-error `<Alert severity="error">` slot renders from local state
  now (nothing sets it yet); the status-code mapping is wired in step 1.6.
- Pending state per ui-spec §7: all inputs + submit disabled, spinner in the
  button — driven by the mutation's `isPending` (the stub resolves
  immediately; the wiring lands in 1.6 with no component changes).
- Submit handlers call only the stub `useLogin`/`useRegister` — **all**
  request logic stays in `hooks/useAuth.ts` so step 1.6 swaps internals
  without touching these components.
- Accessibility per ui-spec §7: `autoFocus`, `autoComplete`
  (`username`/`current-password`/`new-password`), Enter submits via
  `type="submit"`.
- All strings via react-i18next with the exact keys from ui-spec §6.

## Out of scope (later steps)

- Real API calls, CSRF header, 401 handling, redirect-after-login,
  authenticated-user redirect away from `/login`/`/register` → step 1.6.
- Guards, admin shell, AppLayout nav/account changes → step 1.4.

## Verification

- `pnpm tsc --noEmit` passes (and `pnpm lint` if configured).
- `/login` and `/register` render at `localhost:5173` inside the existing
  AppBar chrome; theme toggle still works on both.
- Invalid input (short password, bad username charset, mismatched confirm)
  shows helper-text errors and blocks submit; valid submit is a no-op.
- All strings come from `translation.json` (spot-check: temporarily rename a
  key → the raw key renders).

## Risks / notes

- Do not invent request logic here — the pinned API contract is what 1.6
  wires. If something seems unspecified, it is specified in
  `shared-knowledge.md` or `ui-spec.md`; re-read before improvising.
- Keep the stub file header comment marking it as replaced in 1.6.
