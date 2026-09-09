# home

The signed-in landing screen: greets the user and lets them sign out.

## Owns

- `HomeRoute`, the `/` screen.
- `AppShell`, the app frame (bar with title/action slot, content container).

## Surface

- Nothing here is imported by another module; `HomeRoute` is the app's leaf.

## Notes

- `home` imports from `auth` (`SignOutButton`, `useSignOut`,
  `useCurrentUser`) — the one permitted cross-module edge. `HomeRoute` owns
  the single `useSignOut()` instance, feeding button and error alert from it.
- `AppShell` lives here, not `src/components/`, since `HomeRoute` is its
  only caller; it graduates unchanged once a second module renders it (D1).
