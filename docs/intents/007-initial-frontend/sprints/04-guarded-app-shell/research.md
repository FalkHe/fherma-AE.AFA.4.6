---
author: fhit:architect
owner: agent
created: 2026-09-22
---
# Research: 007/04 guarded app shell

> **Blocked on a split.** The brief bundles five independent deliverables; the contract below runs
> ~1200 words against the 1000 cap and the work is ~3–5 h, not 1–2 h. Proposed halves, each
> independently mergeable, sharing these facts and interfaces verbatim:
> **04a — one guard, one header, one account menu** (AC1, AC3, AC4 · WI1, WI2, WI3, WI5) ·
> **04b — back to the page you asked for** (AC2, AC5 · WI4 plus the second protected address).

## Facts

**Routing.** `App.tsx:13-39` is one flat `<Routes>`: `/` wraps `<HomeRoute/>` in `<RequireAuth>`
(`:14-21`), `/signin` (`:22-29`) and `/signup` (`:30-37`) wrap theirs in `<RequireAnonymous>`, `*` →
`<Navigate to="/" replace/>` (`:38`) — three repeats. `react-router@8.3.1` (`pnpm-lock.yaml`): a
pathless layout route is `<Route element={<Layout/>}>…</Route>` with `<Outlet/>` inside — source
context7 (`/websites/reactrouter`, declarative mode) and the installed
`dist/production/index.d.ts`, which exports `Outlet` from the package root beside `Navigate`.

**Return address.** `RequireAuth.tsx:63-66` already records it, redirecting with
`state={{ from: location, reason? }}`; `AuthRedirectState` is exported at `:16-19`. `from` is a full
`Location`, and the installed d.ts has `Location extends Path`, `To = string | Partial<Path>`, so
pathname, search and hash survive `navigate(from)`. `location.state` is the only mechanism the
router offers. `RequireAnonymous.tsx:25-27` ignores `from`, always sending a signed-in visitor to `/`.

**The code note (AC5).** `useSignIn.ts:1-4`: *"Deliberate ordering (step-0.1.md §6.2): write the
cache, then navigate to the attempted location (`from`) or `/`. See shared-knowledge.md 'Known
future work' — the step that adds a second protected route must flip this to navigate-then-write,
the way `useSignOut` already does."* Today `:26-28` writes `["currentUser"]`, then navigates. Why
wrong (`docs/roadmap/phase-0/shared-knowledge.md:405-412`): once the cache holds a user,
`RequireAnonymous` — still mounted on `/signin` — can win the race with its own
`<Navigate to="/" replace>`, so the visitor lands on `/`, not `from`; invisible while `/` is the
only protected address. Flipped, the router leaves `/signin` before the guard sees a user, so a
deep-link sign-in observably ends on the requested address. `useSignOut.ts:31-35` is the working
model (navigate → clear CSRF → write cache).

**Shell.** `modules/home/components/AppShell.tsx:18-61`: `AppBar`/`Toolbar`, `title` as
`<Typography variant="h6" component="p">` (`:37-51`), an `action` slot (`:52`),
`Container maxWidth="sm"` (`:56`); props `{title, action?, children}` (`:12-16`). Owned by `home`
(`README.md:8,19-20`: "graduates unchanged once a second module renders it"). Its only caller
`HomeRoute.tsx:34-46` also owns `useSignOut()` and renders `SignOutButton` plus the sign-out error
alert (`:36-42`).

**Boundaries — `structure.test.ts`.** `:154-203` pins `core/` to an exact file list (`:156-188`),
bans `.tsx` there (`:197`) and bans `modules/` imports — but that scan reads `.ts` only (`:198`), so
a `.tsx` in `core/` would escape it. `:205-209` bans `.ts(x)` under `src/components/`. `:211-218`
pins AppShell to `modules/home/components/`, importing nothing from a module. `:220-255` is the one
permitted cross-module edge, `home → auth` limited to
`["SignOutButton","useSignOut","useCurrentUser"]` (`:228`), `auth → home` forbidden (`:246-252`).
`:113-120` / `:122-142` ban hex/`rgb()`/`hsl()` in `.ts|.tsx|.json` and in every `.css` outside
`core/theme/tokens/`; the theme carries `palette.divider`, `shape.borderRadius*`, `shadows[…]`
(`core/theme/index.ts:32-36,46-75`). `:73-111` allows one icon package, `lucide-react`
(`package.json:26`), imported nowhere yet.

**Current user / sign out.** `useCurrentUser.ts:33-47` returns
`{user, sessionExpired, isPending, isError, refetch}`; `CurrentUser` is `UserRead` =
`{id, username, createdAt}` — no e-mail field exists. `useSignOut()` (`useSignOut.ts:15-36`) is a
mutation; 401 counts as success, 403/5xx surface as `mutation.error`.

**Design.** `docs/design/…/project/Dashboard.dc.html:15-34` is the header: sticky hairline bar,
a `--accent-quiet` badge with the lucide `flame` icon plus the small-caps wordmark, and a round
`aria-label="Account"` button carrying one initial that opens a panel of bold name, e-mail line
(omitted — none exists), hairline and a `log-out` "Sign out" row. `CampaignRun.dc.html:13-20` puts
a "‹ Campaigns" link where the wordmark sits.

**i18n.** Namespaces `common`, `auth`, `home` (`core/i18n/index.ts:10-12`), keys typed off the
English resources (`i18n.d.ts`). Present: `common:app.title`, `auth:signOut.action`,
`auth:signOut.error`. One new key only (below) — no new namespace, no new pinned `core/` entry.

**Tests that move.** `HomeRoute.test.tsx:65-80, :83-105, :106-126, :128-144` drive the sign-out
button `HomeRoute` will no longer own; `:61-62` asserts the wordmark is a `P`.

## Work items

- **WI1 — one guard for the whole signed-in area.** Rewrite `App.tsx` into two pathless layout
  routes. Checks: `/` still renders the landing screen when signed in; signed out reaches `/signin`;
  no header while the session read is pending or errored; `/signin`/`/signup` still bounce a
  signed-in visitor. Consumes WI2 and WI3, writable in parallel against them.
- **WI2 — the frame wears the designed header.** Move `AppShell` to `core/layout/`, drop `title`,
  render the wordmark (badge + flame + `common:app.title`), keep the `action` slot. Checks: the
  wordmark shows and is not a heading; the bar is `role="banner"`; no colour or radius literal.
- **WI3 — the account menu.** New `AccountMenu` in `auth` owning `useCurrentUser()` and
  `useSignOut()`; `HomeRoute` loses sign-out; `SignOutButton` goes. Checks: trigger named "Account",
  showing the initial; panel carries the username and "Sign out"; signing out lands on `/signin` and
  Back does not restore the page; 403/500 keeps the visitor signed in with the error in the open
  panel; 401 signs out silently. Owns the migrated `HomeRoute` cases.
- **WI4 — signing in returns to the requested address.** Flip `useSignIn` to navigate-then-write,
  delete the note, let `RequireAnonymous` honour `from`. Checks: sign-in after a redirect from a
  deep address ends there, not `/`; a direct `/signin` still ends on `/`; query and fragment
  survive. Needs WI1 (a second protected address to aim at).
- **WI5 — the structure test records the new shape**, then `modules/home/README.md`,
  `modules/auth/README.md`, `docs/architecture.md:27`. Last and alone: one editor for that file.

WI2 ∥ WI3 → WI1 → WI4 → WI5.

## Interfaces

Created: `frontend/src/core/layout/AppShell.tsx`,
`frontend/src/modules/auth/components/AccountMenu.tsx` (+ `AccountMenu.test.tsx`). Deleted:
`frontend/src/modules/home/components/AppShell.tsx`,
`frontend/src/modules/auth/components/SignOutButton.tsx`.

```ts
// core/layout/AppShell.tsx — MUI, lucide-react, react-i18next only; never modules/
export interface AppShellProps { action?: ReactNode; children: ReactNode }
export function AppShell(props: AppShellProps): ReactElement   // renders common:app.title itself
// modules/auth/components/AccountMenu.tsx
export function AccountMenu(): ReactElement                    // no props
```
`AccountMenu` trigger: `aria-haspopup="menu"`, accessible name `t("auth:account.open")`, content
`user.username[0].toUpperCase()` (empty while unknown). Panel: username, divider, item labelled
`auth:signOut.action`; on failure a `role="alert"` with `auth:signOut.error` inside the open panel.

Route tree (WI1) — the guard sits *outside* the shell, so no header flashes while pending:
```tsx
<Routes>
  <Route element={<RequireAuth><AppShell action={<AccountMenu />}><Outlet /></AppShell></RequireAuth>}>
    <Route path="/" element={<HomeRoute />} />
  </Route>
  <Route element={<RequireAnonymous><Outlet /></RequireAnonymous>}>
    <Route path="/signin" element={<SignInRoute />} />
    <Route path="/signup" element={<SignUpRoute />} />
  </Route>
  <Route path="*" element={<Navigate to="/" replace />} />
</Routes>
```

`useSignIn.onSuccess` (WI4), exactly `useSignOut`'s order:
```ts
navigate(state?.from ?? "/", { replace: true });
queryClient.setQueryData<CurrentUserState>(["currentUser"], { user, sessionExpired: false });
```
and `RequireAnonymous` returns `<Navigate to={state?.from ?? "/"} replace />`.

i18n (WI3, `core/i18n/locales/en/auth.json`): `"account": { "open": "Account" }`. Nothing else.

`structure.test.ts` (WI5): add `"layout/AppShell.tsx"` to the pinned `core/` list; replace the
blanket `.tsx` ban with "allowed only under `core/layout/`"; widen `:198`'s scan from `.ts` to
`.ts|.tsx`; retarget 42(b) to `src/core/layout/AppShell.tsx`; reduce 42(c)'s `allowedNames` to
`["useCurrentUser"]`, keeping `auth → home` forbidden; assert the two deleted files are gone.

## Open questions

**Product-visible — decide before the sprint starts:**

1. **AC2 needs a second protected address:** everything outside the route table is swallowed by the
   catch-all, so "the address you asked for" is always the landing page today. Recommended: add the
   run screen's address now as an empty framed placeholder sprint 05 fills. Otherwise AC2 is proven
   by tests only.
2. **Where a failed sign-out speaks.** Recommended: inside the open account menu. Today it sits
   above the greeting; a toast is the third option.
3. **The run screen's back link.** The design puts "‹ Campaigns" where the wordmark sits; with one
   header for every signed-in page it becomes part of the page. Recommended: accept, and let sprint
   05 place it at the top of the run screen.

**Internal:** the flame badge is rebuilt with `lucide-react`'s `Flame`, not imported from the design
bundle; the content container keeps its width until a screen needs more; AC5 removes the note in the
code — the roadmap copy stays, being history.
