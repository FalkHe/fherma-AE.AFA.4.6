# auth

Sign-in, sign-up and the route guards that decide who may see what. Owns
knowing who the current user is and getting them in or out of a session.

## Owns

- The sign-in and sign-up screens, and their client-side validation rules.
- `RequireAuth` / `RequireAnonymous`, the route guards (UX only, not the
  security boundary), and the signed-in user as server state.

## Surface

- `home` imports `useCurrentUser` — the only permitted cross-module edge in
  this app. `AccountMenu` (header account control, sign-out included) owns
  `useSignOut` itself and is not imported by `home`. Everything else is
  internal.

## Notes

- The expired-versus-never-signed-in distinction comes off the server's 401
  `code` on every fetch, not client-side memory — the guards hold no state.
- `RequireAuth` is the only component that redirects to `/signin` on an expiry.
  A deliberate sign-out navigates from `useSignOut`, which clears the cache
  afterwards, so the two can never both fire.
