# home

The signed-in screens: the landing greeting and the (currently empty)
dashboard.

## Owns

- `HomeRoute`, the `/` screen.
- `DashboardRoute`, the `/dashboard` screen — a heading only until sprint 07
  fills it in.

## Surface

- Nothing here is imported by another module; both routes are app leaves.

## Notes

- `home` imports `useCurrentUser` from `auth` — the one permitted cross-module
  edge. Sign-out itself lives entirely in `auth`'s `AccountMenu`, which owns
  its own `useSignOut()` instance.
- `AppShell` moved to `core/layout/` once a second module (`App.tsx`) needed
  to render it — the guarded-shell composition itself lives in `App.tsx`, not
  here (sprint 007/04 WI1); neither `HomeRoute` nor `DashboardRoute` renders
  its own frame anymore.
