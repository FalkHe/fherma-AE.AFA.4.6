# auth

Owns the credential/session lifecycle: registration, sign-in, sign-out, and
the cookie session proving a request is signed in. `users` owns the person
record.

## Owns

- The `sessions` table (`UserSession`): hashed token, CSRF token, `expires_at`.

## Surface

- `CurrentAuth` / `CsrfAuth` — the latter also requires a matching
  `X-CSRF-Token` header.
- `service.create_session` / `resolve_session` / `delete_session`.
- `POST /register`, `/sign-in`, `/sign-out` (`frontend/openapi.json`).

## Notes

- No cookie yields `NOT_AUTHENTICATED`; an unresolved cookie (incl. expired —
  `resolve_session` leaves the row) yields `SESSION_EXPIRED`.
- `SignInRequest` skips the username pattern, so a bad username fails 401, not
  a shape-leaking 422 (§5.4, `step-0.1.md`).
- The `ApiError` handler clears the session cookie on `SESSION_EXPIRED`, not
  `require_auth` — a dependency that raises has its injected `Response`
  discarded, so it cannot clear the cookie itself.
