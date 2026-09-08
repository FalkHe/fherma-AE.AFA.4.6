---
title: "Phase 0 / Step 0.1 – UI spec: authentication and the authenticated shell"
created: 2026-09-08
status: revised-after-review
owner: ux-designer
tags:
  - phase-0
  - ui-spec
  - auth
---

# Phase 0 · Step 0.1 — UI spec

Scope: **sign-up**, **sign-in**, and a **blank authenticated home page** plus the
app shell that holds it. Nothing else. These are the first screens in the
repository, so this document also pins the conventions the later phases inherit:
i18n namespaces and key shape, where auth UI lives in the module tree, how
server errors reach the screen, and how focus is managed on transitions.

**Revision after the spec review** (owner rulings; the design itself is
unchanged):

- `AppShell` moves to `modules/home/components/`, and `src/components/` is
  empty in phase 0 (§1, §3).
- `HomeRoute` owns the single `useSignOut()` instance and renders the sign-out
  alert (§3.3, §5, UI-27).
- The server-422 → field-error mapping is dropped (§5.3).
- Acceptance criteria carry a `UI-` prefix; UI-1 … UI-38 keep their numbers and
  UI-39 … UI-43 are appended (§12).
- MUI is **v9**, with no pre-v9 fallback anywhere (§11).
- The open-questions block is struck: all seven are answered, and
  `step-0.1.md` §6.3/§6.4 is the authoritative resolution table this document
  points at instead of restating (§11).
- The expired-versus-never-authenticated split is read off the response code
  (`SESSION_EXPIRED` vs `NOT_AUTHENTICATED`), and `useCurrentUser()` keeps no
  `wasAuthenticated` ref (§6.3).
- The `RequireAnonymous` pending state (§6.4), the single-`<h1>`-and-focus-
  target resolution (§3.3, §6.5), the `ThemeProvider` props (§10) and the
  `AuthCard` `title` prop (§2) are pinned rather than left ambiguous.

## 0. Design ground rules (binding on this step)

1. **Plain MUI, default theme.** No custom palette, no custom typography scale,
   no bespoke components, no genre theming. Every colour, radius and spacing
   value comes from the default theme (`theme.spacing`, `sx={{ p: 3 }}`, the
   default `primary`/`error`/`warning` palettes). If a value looks like
   `#4a2c12`, it is wrong.
2. **No icons anywhere in this step.** No icon package is needed, and none must
   be added. The password field has **no visibility toggle** and the shell has
   **no hamburger** — both would need an icon and neither is required here.
3. **Every string is an i18n key.** Section 7 is the complete copy table.
4. **No decorative imagery, no marketing copy, no "coming soon".**

## 1. Routes, module layout, file ownership

```
frontend/src/
├── main.tsx                       # React root: providers only
├── App.tsx                        # the route table, nothing else
├── core/
│   ├── theme.ts                   # createTheme() – light + dark schemes
│   ├── i18n/
│   │   ├── index.ts               # i18next init, en resources
│   │   ├── i18n.d.ts              # CustomTypeOptions -> compile-checked keys
│   │   └── locales/en/{common,auth,home}.json
│   ├── queryClient.ts             # TanStack Query client
│   └── api/                       # fetch wrapper + error normalisation
└── modules/
    ├── auth/
    │   ├── validation.ts          # the rule constants + field validators
    │   ├── hooks/                 # no modules/auth/api.ts: each hook calls
    │   │   │                       #   core/api directly (step-0.1.md R4 and
    │   │   │                       #   criterion 42(c), which greps for it)
    │   │   ├── useCurrentUser.ts  # session read; query key ["currentUser"]
    │   │   ├── useSignIn.ts
    │   │   ├── useSignUp.ts
    │   │   └── useSignOut.ts
    │   ├── components/
    │   │   ├── AuthCard.tsx       # shared by the two auth routes
    │   │   ├── SignInForm.tsx
    │   │   ├── SignUpForm.tsx
    │   │   ├── SignOutButton.tsx  # presentational; rendered by HomeRoute
    │   │   │                       #   into AppShell's `action` slot
    │   │   ├── RequireAuth.tsx    # guard for authenticated routes
    │   │   └── RequireAnonymous.tsx
    │   └── routes/
    │       ├── SignInRoute.tsx
    │       └── SignUpRoute.tsx
    └── home/
        ├── components/
        │   └── AppShell.tsx      # app frame: title + action slot + children,
        │                          #   auth-agnostic. Lives here in phase 0
        │                          #   because HomeRoute is its only caller.
        └── routes/HomeRoute.tsx   # owns useSignOut(); composes the shell
```

`src/components/` **does not exist in phase 0**. Nothing in this step has two
module callers, so the shared directory has no members yet.

| Path | Route element | Guard |
|---|---|---|
| `/signin` | `SignInRoute` | `RequireAnonymous` |
| `/signup` | `SignUpRoute` | `RequireAnonymous` |
| `/` | `HomeRoute` (which renders `AppShell`) | `RequireAuth` |
| anything else | redirect to `/` (`replace`) | — |

**Why `AppShell` lives in `modules/home/` — and how it graduates.** The rule is
that shared UI needs two or more module callers. `AppShell` has exactly **one**:
`/` is the only route that renders it, so `HomeRoute` is its sole caller. It is
`HomeRoute` — not `modules/auth` — that imports `SignOutButton` and passes it
into the `action` slot, so `modules/auth` never calls `AppShell` at all. One
caller means it belongs to that caller's module: `modules/home/components/`.

The component itself is built for sharing and is **not** to be changed when it
moves: it takes `title`, an `action?: ReactNode` slot and `children`, and
**imports nothing from `modules/auth`**. That construction is what makes the
graduation to `src/components/AppShell.tsx` automatic rather than a judgement
call — the day a second module renders the shell, the import path moves and
nothing else does. Had the shell imported the sign-out hook directly, it would
have been auth-coupled and could never graduate; keeping auth knowledge out of
the frame is the whole point of the `action` prop.

`AuthCard` is the counter-example that confirms the rule from the other side: it
has two callers (`SignInRoute`, `SignUpRoute`) but **both are inside
`modules/auth`**, so it stays in that module. Two callers in one module is not
two module callers.

## 2. The shared auth page frame (`AuthCard`)

Both auth screens are the same frame with different contents. `AuthCard` props:
`title: string` (already translated by the caller — the card never calls `t()`
for it), `children` (the form), `footer` (the cross-link line). There is no
`titleKey` prop.

```
DESKTOP (>= 600 px)                          MOBILE (< 600 px, 360 px shown)
┌──────────────────────────────────────────┐  ┌────────────────────────┐
│                                          │  │  AI Dungeon Master     │
│            AI Dungeon Master             │  │ ┌────────────────────┐ │
│                                          │  │ │ Sign in            │ │
│      ┌──────────────────────────────┐    │  │ │                    │ │
│      │ Sign in              (h5)    │    │  │ │ ┌────────────────┐ │ │
│      │                              │    │  │ │ │ Username       │ │ │
│      │ [ (form-level Alert here) ]  │    │  │ │ └────────────────┘ │ │
│      │ ┌──────────────────────────┐ │    │  │ │ ┌────────────────┐ │ │
│      │ │ Username                 │ │    │  │ │ │ Password       │ │ │
│      │ └──────────────────────────┘ │    │  │ │ └────────────────┘ │ │
│      │ ┌──────────────────────────┐ │    │  │ │ ┌────────────────┐ │ │
│      │ │ Password                 │ │    │  │ │ │    Sign in     │ │ │
│      │ └──────────────────────────┘ │    │  │ │ └────────────────┘ │ │
│      │ ┌──────────────────────────┐ │    │  │ │ New to the game?   │ │
│      │ │         Sign in          │ │    │  │ │ Create an account  │ │
│      │ └──────────────────────────┘ │    │  │ └────────────────────┘ │
│      │ New to the game?             │    │  └────────────────────────┘
│      │ Create an account            │    │
│      └──────────────────────────────┘    │  (page top-aligned, py=4, so the
│                                          │   on-screen keyboard does not
└──────────────────────────────────────────┘   push the card off-centre)
```

Structure and the props that matter:

```tsx
// SKETCH — illustrates component choice and props. Not landable code.
<Box sx={{ minHeight: '100dvh', display: 'flex',
           alignItems: { xs: 'flex-start', sm: 'center' },
           justifyContent: 'center', py: { xs: 4, sm: 0 } }}>
  <Container maxWidth="xs" disableGutters={false}>
    <Typography variant="h6" component="p" align="center" sx={{ mb: 2 }}>
      {t('app.title')}
    </Typography>
    <Paper elevation={1} sx={{ p: { xs: 2, sm: 3 } }}>
      <Stack spacing={2}>
        <Typography variant="h5" component="h1">{title}</Typography>
        {children /* the <form> */}
        <Divider flexItem />
        {footer}
      </Stack>
    </Paper>
  </Container>
</Box>
```

## 3. Component table

### 3.1 Sign-in (`SignInRoute` → `AuthCard` + `SignInForm`)

| Region | MUI component + props that matter | Data source |
|---|---|---|
| Page frame | `Box` / `Container maxWidth="xs"` / `Paper elevation={1}` | — |
| App name | `Typography variant="h6" component="p"` | `common:app.title` |
| Heading | `Typography variant="h5" component="h1"` | `auth:signIn.title` |
| Session-expired notice | `Alert severity="warning"` (only when router state says so) | `auth:signIn.sessionExpired` |
| Form-level error | `Alert severity="error" ref tabIndex={-1}` (MUI sets `role="alert"`) | mapped server error |
| Form | `<form onSubmit>` inside `Stack spacing={2}` | — |
| Username | `TextField` — `id="signin-username"`, `name="username"`, `label`, `fullWidth`, `required`, `autoComplete="username"`, `autoFocus`, `error`, `helperText`, `slotProps={{ htmlInput: { maxLength: USERNAME_MAX } }}` | local state |
| Password | `TextField type="password"` — `id="signin-password"`, `autoComplete="current-password"`, otherwise as above | local state |
| Submit | `Button type="submit" variant="contained" fullWidth size="large" loading={isPending}` | mutation state |
| Footer link | `Typography variant="body2"` + `Link component={RouterLink} to="/signup"` | `auth:signIn.noAccount`, `auth:signIn.createAccount` |

No password hint and no charset hint on sign-in: the rules are not news to a
returning user and printing them here only helps an attacker.

### 3.2 Sign-up (`SignUpRoute` → `AuthCard` + `SignUpForm`)

Identical structure, with these differences:

| Region | Difference |
|---|---|
| Heading | `auth:signUp.title` |
| Username | `id="signup-username"`, `autoComplete="username"`, `helperText` defaults to `auth:fields.username.hint` (interpolated rule numbers) and is **replaced** by the validation message when invalid |
| Password | `id="signup-password"`, `autoComplete="new-password"`, `helperText` defaults to `auth:fields.password.hint`, replaced when invalid |
| Submit | `auth:signUp.submit` / `auth:signUp.submitting` |
| Footer link | `auth:signUp.haveAccount` + `Link to="/signin"` (`auth:signUp.signInLink`) |
| Server error | taken username is a **field** error on username, not a form-level Alert (see 5.2) |

**Deliberately absent**: confirm-password field, password strength meter,
visibility toggle, terms checkbox. The briefing pins "username + password
only". The typo risk of a single unmasked password field with no confirmation
is accepted for this step.

### 3.3 Authenticated shell + home

```
DESKTOP                                       MOBILE (360 px)
┌──────────────────────────────────────────┐  ┌────────────────────────┐
│ AI Dungeon Master            [Sign out]  │  │ AI Dungeon Ma… [Sign…] │  AppBar
├──────────────────────────────────────────┤  ├────────────────────────┤
│                                          │  │                        │
│   Welcome, thorin.                       │  │  Welcome, thorin.      │  main
│                                          │  │                        │
└──────────────────────────────────────────┘  └────────────────────────┘
```

| Region | MUI component + props | Data source |
|---|---|---|
| Bar | `AppBar position="static"` + `Toolbar` | — |
| Title | `Typography variant="h6" component="p" noWrap sx={{ flexGrow: 1 }}` | `common:app.title` |
| Action slot | `AppShell` prop `action?: ReactNode` | filled by `HomeRoute` with `<SignOutButton />` |
| Sign out | `Button color="inherit" loading={isPending}` | `auth:signOut.action` |
| Content | `Box component="main"` > `Container maxWidth="sm" sx={{ py: 4 }}` | `children` |
| Sign-out error | `Alert severity="error" tabIndex={-1}` at the top of the container, rendered by `HomeRoute` into `children` | `auth:signOut.error` |
| Greeting | `Typography variant="h5" component="h1" tabIndex={-1}` | `home:greeting` with `{{username}}` from `useCurrentUser()` |

The bar keeps a text "Sign out" button at every width — it fits 360 px, needs
no icon and needs no menu. `noWrap` on the title truncates instead of wrapping.
Nothing else is on the page: no cards, no placeholders, no teasers.

**The AppBar title is branding, not the document heading.** It is
`component="p"`, exactly like the app name above the auth card (§2), and the
page's `<h1>` lives in `children`. On `/` that `<h1>` is the greeting. This
keeps `AppShell` free of any claim on the heading outline, so a later phase
route mounting inside it supplies its own `<h1>` without fighting the frame —
and it makes the post-navigation focus target (§6.5) the element that actually
describes the page.

**Composition — one owner for the sign-out mutation.** `HomeRoute` calls
`useSignOut()` **once** and renders both consumers of that one mutation
instance: it passes `<SignOutButton onClick={…} loading={…} />` into
`AppShell`'s `action` slot and renders the error `Alert` into `children`. Two
components calling `useSignOut()` would get two independent mutation instances,
so the button's pending state and the alert's error would come from different
mutations. `SignOutButton` is therefore presentational: it holds no hook, and
neither a context nor a store is introduced.

## 4. Validation — client side

The numbers live in **one** place, `modules/auth/validation.ts`, and are
interpolated into the copy, so the translation file never contains a number:

```ts
// SKETCH. The values come from step-0.1.md §6.4, which is the single source of
// truth for the numbers and the pattern; this file transcribes them and adds
// nothing. Exports: USERNAME_MIN, USERNAME_MAX, USERNAME_PATTERN,
// PASSWORD_MIN, PASSWORD_MAX — plus the two field validators that use them.
export const USERNAME_MIN = /* §6.4 */;
```

| Field | Rule | Message key |
|---|---|---|
| username | non-empty after `trim()` | `auth:validation.username.required` |
| username | length ≥ `USERNAME_MIN` | `auth:validation.username.tooShort` (`{{min}}`) |
| username | length ≤ `USERNAME_MAX` | `auth:validation.username.tooLong` (`{{max}}`) |
| username | matches `USERNAME_PATTERN` | `auth:validation.username.charset` |
| password | non-empty | `auth:validation.password.required` |
| password | length ≥ `PASSWORD_MIN` | `auth:validation.password.tooShort` (`{{min}}`) |
| password | length ≤ `PASSWORD_MAX` | `auth:validation.password.tooLong` (`{{max}}`) |

Rules run in that order per field; the **first** failure is shown. Only one
message per field is ever visible.

**Timing.** Validate on `submit`, and on `blur` for a field the user has
already edited. Never validate a field the user has not touched. On `change`,
clear that field's message immediately (do not re-validate mid-typing) and
clear any form-level Alert. `maxLength` on the username input is a courtesy
stop, not the validation.

**Sign-in validates presence only** (both fields non-empty). Applying charset
or length rules on sign-in would tell an attacker what a valid username looks
like and would lock out accounts created under earlier rules. Client-side
"required" is the *only* sign-in validation.

Username is trimmed before validation and before submission. Password is sent
verbatim, never trimmed.

## 5. Server errors → screen

The wire error envelope is `{"error": {"code", "message", "details"}}`
(`.claude/CLAUDE.md`, landed conventions). `core/api` normalises every failure
into `{ code, status }`; the forms map `code` to a key. **`message` from the
backend is never rendered** — all copy is local, so it is translatable.

| Situation | HTTP / code | Where it shows | Key |
|---|---|---|---|
| Sign-in credentials wrong | 401 `INVALID_CREDENTIALS` | form-level `Alert severity="error"` | `auth:signIn.error.invalidCredentials` |
| Sign-up username taken | 409 `USERNAME_TAKEN` | username field `error` + `helperText` | `auth:signUp.error.usernameTaken` |
| Session missing/expired | 401 `NOT_AUTHENTICATED` / `SESSION_EXPIRED` | never in the form — the guard redirects on the next mount of the session query (nothing invalidates it; 6.3), and the code decides whether a warning shows | `auth:signIn.sessionExpired`, for `SESSION_EXPIRED` only |
| Sign-out failed | 403 / 5xx / unmapped / network — **not** 401, which is the deliberate case (R10) | `Alert severity="error"` at the top of the shell's main container, **rendered by `HomeRoute`** (3.3) | `auth:signOut.error` |
| Network unreachable / fetch threw | — | form-level `Alert severity="error"` | `common:errors.network` |
| 422 `VALIDATION_ERROR`, 500, or any unmapped code | 422 / 5xx / unknown | form-level `Alert severity="error"` | `common:errors.unexpected` |

**5.1 No user-existence leak.** Sign-in has exactly one failure message for
"wrong username", "wrong password" and "no such user". It is the same string,
shown in the same place, and neither field is marked `error` (a red username
field would itself be a signal). Sign-in must also not vary its *loading time*
visibly — that is a backend concern. Phase 0 has no rate limiting and so no
lockout copy either (`step-0.1.md` §6.4).

**5.2 The taken-username case is a field error on purpose.** It is
actionable — the user must change that specific field — so it reads as
`helperText` on the username field, the field is focused, and the username
value is **kept** so the user can edit rather than retype. Password is kept
too. No form-level Alert in this case (one message, one place).

**5.3 A 422 is treated as an unexpected failure, not as field errors.** The
client mirrors the server's rules (section 4) and blocks a non-conforming
payload before it is sent, so a 422 can only mean client and server rules have
drifted apart — a bug, not something the user can act on. There is deliberately
**no** mapping from the 422 `details` payload onto field errors: it would be
unreachable code with nothing to prove it, and neither form parses `details`.
A 422 renders `common:errors.unexpected` in the form-level Alert, exactly like a
500.

**5.4 Never a frozen screen.** Every mutation drives a `Button loading` state
(3.1). Neither auth form uses a blocking backdrop or a modal: the fields stay
readable, and the only disabled things are listed in section 6.

## 6. State matrix

### 6.1 Sign-in (`/signin`)

| State | What the user sees | Disabled / interactive | Focus |
|---|---|---|---|
| Initial | Card, empty fields, no messages | all interactive | username (`autoFocus`) |
| Returning from `RequireAuth` because unauthenticated | identical to initial — no message; the user never had a session, so nothing "went wrong" | as initial | username |
| Returning because the session expired | `Alert severity="warning"` above the fields | as initial | the Alert (`tabIndex={-1}`, focused once on mount) |
| Focused field | default MUI focus ring + floating label (theme default, no override) | — | — |
| Client-side invalid on submit | offending field(s) `error`, message as `helperText` | all interactive; **no** request sent | first invalid field |
| Submitting | `Button loading`, label → `auth:signIn.submitting` | submit button disabled by `loading`; both `TextField`s get `disabled` so the payload cannot change mid-flight; the sign-up `Link` stays clickable | stays where it was (button) |
| Invalid credentials | form-level error Alert; password field **cleared**, username kept | all interactive again | the Alert |
| Network down / 422 / 500 | form-level error Alert (`common:errors.network` / `.unexpected`); **both values kept** so the user can just resubmit | all interactive again | the Alert |
| Success | no success message — the card unmounts and the app shell renders | — | see 6.5 |

### 6.2 Sign-up (`/signup`)

| State | What the user sees | Disabled / interactive | Focus |
|---|---|---|---|
| Initial | Card, empty fields, both `helperText` hints showing the rules | all interactive | username (`autoFocus`) |
| Client-side invalid | hint replaced by the validation message, field `error` | no request sent | first invalid field |
| Submitting | `Button loading`, label → `auth:signUp.submitting`; fields `disabled` | as 6.1 | button |
| Username taken (409) | username `error`, `helperText` = taken message; both values kept | all interactive again | username field, cursor at end of the existing value |
| Network down / 422 / 500 | form-level error Alert (`common:errors.network` / `.unexpected`), values kept | all interactive again | the Alert |
| Success | card unmounts; see 6.5 | — | — |

### 6.3 Home (`/`) and the shell

| State | What the user sees | Focus |
|---|---|---|
| Session unknown (first paint, session query `pending`) | full-viewport centred `CircularProgress` with `aria-label={t('app.loading')}`, rendered **by the guard**, no AppBar yet — so no shell flashes before we know who the user is | body |
| Authenticated | AppBar + greeting | the greeting `<h1>` on arrival (6.5); first *tab* stop is the Sign out button |
| Session query failed with 401 `SESSION_EXPIRED` | `Navigate to="/signin"` `replace` with state `{ from, reason: 'sessionExpired' }` | see 6.1 |
| Session query failed with 401 `NOT_AUTHENTICATED` | `Navigate to="/signin"` `replace` with state `{ from }` and **no** `reason`, so no message shows | see 6.1 |
| Session query failed for a network/5xx reason | centred `Alert severity="error"` (`common:errors.network` / `.unexpected`) with a `Button` (`common:actions.retry`) that refetches. **Not** a redirect to sign-in — the user may well still be signed in | the retry button |
| Signing out | Sign out `Button loading`; the greeting stays visible and readable | button |
| Sign-out failed | `Alert severity="error"` (`auth:signOut.error`) at the top of the main container, above the greeting, rendered by `HomeRoute` (3.3); still signed in | the Alert |
| Signed out | redirect to `/signin` `replace`, session cache cleared | see 6.5 |

An **unauthenticated visitor hitting `/`** therefore never sees the shell: the
guard shows the spinner while the session read is in flight and then replaces
the location with `/signin`, remembering `from` in router state.

A **session the server no longer recognises** is discovered when the
`["currentUser"]` query is *read on a mount* — and only then. Step 0.1 gives
that query `retry: false`, `refetchOnWindowFocus: false`, `staleTime: 30_000`,
no refetch interval and no invalidation from anywhere (`core/api/client.ts`
holds no `QueryClient` reference at all, so it cannot invalidate anything —
`step-0.1.md` R10/D21 forbid a global 401 interceptor). Nothing therefore
re-reads the session while a tab stays open; sign-out is the one deliberate
exception, and it sets the query data to `null` itself. The next mount — a
reload, or a fresh tab — is what surfaces the ended session.

On that mount `RequireAuth` runs and the redirect reason comes off **the
response code**: `GET /api/v1/users/me` answers `SESSION_EXPIRED` for a session
that existed and has ended, and `NOT_AUTHENTICATED` for a caller that never had
one. `SESSION_EXPIRED` → `{ from, reason: 'sessionExpired' }` → the warning
Alert in 6.1; `NOT_AUTHENTICATED` → `{ from }` with no `reason`, so no
message.

`useCurrentUser()` therefore returns only what the screen renders — the user (or
`null`) plus the query's status and error code — and holds **no**
`wasAuthenticated` ref or any other client-side memory of having been signed
in. The split is server truth, read fresh on every attempt, so there is no
second mechanism to keep in sync and "Your session ended." shown to a
first-time visitor stops being a thing that can happen rather than a thing a
ref has to be careful about. UI-28 still proves the user-visible behaviour; it
was written against behaviour, not mechanism.

### 6.4 Anonymous-only guard

An authenticated user who navigates to `/signin` or `/signup` is redirected to
`/` (`replace`), with no message. This keeps the back button from parking a
signed-in user on a dead form.

| State | What the user sees | Focus |
|---|---|---|
| Session unknown (session query `pending`) | the **same** full-viewport centred `CircularProgress` with `aria-label={t('app.loading')}` that `RequireAuth` shows (6.3) — **not** the form | body |
| Anonymous | the auth route | as 6.1 / 6.2 initial |
| Authenticated | `Navigate to="/" replace`, no message | as 6.3 |

**Why the spinner rather than rendering the form immediately.** Both guards read
the one shared session query, so both have exactly the same three answers and
must not disagree about what "unknown" looks like. Painting the form first would
mean a signed-in user who opens `/signin` sees a fully focused username field
flash and vanish, and `autoFocus` would have already stolen the caret from the
page they land on. The pending window exists only on a cold load: after the
first read the query is cached, so an in-app navigation to `/signin` (the
sign-out redirect, the footer links) resolves synchronously and no spinner
appears.

### 6.5 Transitions and where focus lands

| Transition | Navigation | Focus after |
|---|---|---|
| Sign-in success | `navigate(from ?? '/', { replace: true })` | the greeting, which **is** the home `<h1>` (3.3): one element, both the heading and the focus target. It carries `tabIndex={-1}` and is focused programmatically once on mount, so a screen reader announces "Welcome, thorin." rather than leaving the caret on the unmounted form |
| Sign-up success | `navigate('/', { replace: true })` — register returns the session cookie, so there is no detour via `/signin` | as above |
| Sign-out success | `navigate('/signin', { replace: true })` | the sign-in heading (`tabIndex={-1}`) |
| Guard redirect | `<Navigate replace>` | as the target screen's initial state, plus the warning Alert when expired |

`replace` everywhere: the back button must never return the user to a form
whose submission already succeeded.

## 7. Copy and i18n

**Convention pinned by this step** (the repo's only convention from here on):

- One namespace per frontend module, plus `common`. Files:
  `frontend/src/core/i18n/locales/en/{common,auth,home}.json`.
- `defaultNS` is `common`. Other namespaces are always addressed explicitly:
  `t('auth:signIn.title')`, via `useTranslation('auth')` per component.
- Keys are dot-paths of `camelCase` segments, at most three deep, shaped
  `<area>.<element>` / `<area>.<group>.<element>`. Areas mirror the screen
  (`signIn`, `signUp`, `signOut`), cross-screen groups are `fields`,
  `validation`, `errors`, `actions`.
- Interpolation is named and lowercase: `{{username}}`, `{{min}}`, `{{max}}`.
  Numbers never appear literally in a translation file.
- Compile-checked: `core/i18n/i18n.d.ts` declares
  `CustomTypeOptions { defaultNS: 'common'; resources: typeof enResources }`,
  so a key that does not exist is a `tsc` error and `pnpm typecheck` catches it.
- English only in this step. No language switcher is designed — nothing to
  switch to.

### 7.1 `common.json`

| Key | English | Where |
|---|---|---|
| `app.title` | AI Dungeon Master | AppBar title; the line above the auth card |
| `app.loading` | Loading… | `aria-label` of the full-page session spinner |
| `actions.retry` | Try again | retry button when the session read fails for a non-401 reason |
| `errors.network` | Cannot reach the server. Check your connection and try again. | any fetch-level failure |
| `errors.unexpected` | Something went wrong. Please try again. | 500 / unmapped error code |

### 7.2 `auth.json`

| Key | English | Where |
|---|---|---|
| `signIn.title` | Sign in | `/signin` heading + document title |
| `signIn.submit` | Sign in | submit button, idle |
| `signIn.submitting` | Signing in… | submit button while the request is in flight |
| `signIn.noAccount` | New to the game? | footer line on `/signin` |
| `signIn.createAccount` | Create an account | footer link to `/signup` |
| `signIn.error.invalidCredentials` | That username and password do not match. Please try again. | form-level Alert after a 401 |
| `signIn.sessionExpired` | Your session ended. Please sign in again. | warning Alert after an expired-session redirect |
| `signUp.title` | Create an account | `/signup` heading + document title |
| `signUp.submit` | Create account | submit button, idle |
| `signUp.submitting` | Creating account… | submit button while in flight |
| `signUp.haveAccount` | Already have an account? | footer line on `/signup` |
| `signUp.signInLink` | Sign in | footer link to `/signin` |
| `signUp.error.usernameTaken` | That username is already taken. Please choose another. | username `helperText` after a 409 |
| `fields.username.label` | Username | both forms |
| `fields.username.hint` | {{min}}–{{max}} characters. Letters, numbers, underscore and hyphen only. | `/signup` username `helperText`, idle |
| `fields.password.label` | Password | both forms |
| `fields.password.hint` | At least {{min}} characters. | `/signup` password `helperText`, idle |
| `validation.username.required` | Enter a username. | both forms |
| `validation.username.tooShort` | Use at least {{min}} characters. | `/signup` |
| `validation.username.tooLong` | Use at most {{max}} characters. | `/signup` |
| `validation.username.charset` | Use letters, numbers, underscore or hyphen only. | `/signup` |
| `validation.password.required` | Enter a password. | both forms |
| `validation.password.tooShort` | Use at least {{min}} characters. | `/signup` |
| `validation.password.tooLong` | Use at most {{max}} characters. | `/signup` |
| `signOut.action` | Sign out | AppBar button |
| `signOut.error` | Could not sign you out. Please try again. | Alert in the shell after a failed sign-out |

### 7.3 `home.json`

| Key | English | Where |
|---|---|---|
| `greeting` | Welcome, {{username}}. | the only content on `/` |

Document titles are set per route from the keys above (`signIn.title`,
`signUp.title`, `app.title` for home) so the browser tab is not "Vite + React".

## 8. Keyboard, focus order, screen readers

**Tab order, `/signin` and `/signup`** (DOM order, no `tabIndex > 0` anywhere):
form-level Alert (only when present, and only because it carries
`tabIndex={-1}` for programmatic focus — it is *not* a tab stop) → Username →
Password → Submit → footer Link.

**Tab order, `/`**: Sign out button → (nothing else). The greeting heading is
the page's `<h1>` and carries `tabIndex={-1}` for the post-transition focus
move; neither it nor the sign-out error Alert (also `tabIndex={-1}`) is a tab
stop.

- **Enter submits.** Both forms are real `<form>` elements with a
  `type="submit"` button, so Enter from either field submits. No `onKeyDown`
  handlers are needed or wanted.
- Links are `Link component={RouterLink}` — real anchors, so Enter activates
  them and they work with middle-click and "open in new tab".
- While a request is in flight the submit button is disabled by `loading`;
  MUI keeps it focusable and sets the loading indicator's accessible name from
  the button, so focus is not lost and the change of label
  ("Signing in…") is what an assistive technology announces.
- **Field errors**: `TextField error helperText` renders the message in the
  `FormHelperText` that the input already points at via `aria-describedby`, and
  MUI sets `aria-invalid="true"` from `error`. No hand-written `aria-*` is
  needed — that association is the reason to use `TextField` with `helperText`
  rather than a hand-rolled `<Typography>` under the input. Each `TextField`
  needs an explicit unique `id` (see 3.1) for the label/description wiring.
- **Form-level errors**: `Alert` renders `role="alert"`, so the message is
  announced when it appears. It is additionally focused (`tabIndex={-1}`) so a
  keyboard user is put next to the problem and Tab reaches the fields.
- **Status without colour**: every state is carried by text. The error Alert
  and the warning Alert have distinct wording; field errors have a message;
  the loading state changes the button label; the greeting is plain text. No
  state is signalled by colour, weight, or a bare icon anywhere in this step.
- `required` is set on all four inputs, so the label carries the standard
  asterisk and `aria-required` is implied.
- **`autocomplete`**: `username` / `current-password` on sign-in;
  `username` / `new-password` on sign-up. The distinction matters — it is what
  stops a password manager offering to overwrite a stored password during
  sign-in, and what makes it offer to *generate* one during sign-up.
- Landmarks: the shell renders `<AppBar>`(banner) and
  `Box component="main"`. Every screen has exactly one `<h1>`, and it is always
  inside the content, never in the bar: the card heading on the auth pages, the
  greeting on `/`. The app name is `component="p"` in both places. There is no
  navigation landmark — there is nothing to navigate. No skip link is
  specified: with one tab stop before the content on `/` and none on the auth
  pages, it would be noise.

## 9. Responsive behaviour

| Breakpoint | Auth pages | Shell / home |
|---|---|---|
| `xs` (< 600 px) | `Container maxWidth="xs"` with default gutters; card `p: 2`; page top-aligned with `py: 4` so an opening keyboard does not shift the card; submit `fullWidth` | AppBar title `noWrap` truncates; "Sign out" stays a text button; content `Container maxWidth="sm"` with gutters |
| `sm`–`md` | card vertically centred in the viewport, `p: 3`, max ~444 px wide | unchanged |
| `lg`+ | unchanged — the card does **not** grow with the viewport | content column stays `maxWidth="sm"`; the shell does not become a two-column layout |

All of this is default `Container`/`sx` breakpoint syntax; no media queries are
hand-written and `useMediaQuery` is not needed anywhere in this step.

## 10. Light and dark theme

`core/theme.ts`:

```ts
// core/theme.ts — exports the theme and nothing else.
export const theme = createTheme({ cssVariables: true, colorSchemes: { light: true, dark: true } });
```

`main.tsx` — and only `main.tsx` — renders the provider:

```tsx
<ThemeProvider theme={theme} noSsr>
  <CssBaseline />
  …
</ThemeProvider>
```

**Exactly one prop besides `theme`.** `noSsr` is behavioural: with two colour
schemes present, `ThemeProvider` renders twice by default to avoid an SSR
hydration mismatch, and `noSsr` suppresses that second pass. This is a Vite SPA
with no server render, so the guard buys nothing and costs a visible dark-mode
flicker on every reload. `defaultMode` is **not** set: `"system"` is already
the default whenever `colorSchemes` is provided, so passing it would be
redundant. `core/theme.ts` sets neither — props belong to the render site.

- The app follows the **operating-system preference** and switches live with it.
  `cssVariables` avoids a light flash on load. **No theme-toggle UI is designed
  in this step** — there is no settings surface yet to put it in.
- Light: `background.default` white-ish, `Paper` white, AppBar `primary.main`.
  Dark: `background.default`/`paper` `#121212`, AppBar dark surface, text
  `#fff` at the default emphases. All from the MUI default palettes.
- The one thing to check in both schemes: the error `helperText` and the
  `Alert` variants use the default `error`/`warning` palettes, which MUI ships
  contrast-checked for both modes. Because every state also has text, dark mode
  cannot lose information even if a user has a colour-vision deficiency.
- `CssBaseline` must be inside `ThemeProvider`, or dark mode will not reach the
  page background.

## 11. What this spec depends on from the architect

**Nothing is open.** All seven questions this spec once carried (OQ-1 … OQ-7 —
the sign-up session, the username and password rules, the error codes, the
endpoints and CSRF, rate limiting, and the MUI major) are **answered and
binding**. The resolutions are not copied here on purpose: a copy drifts.

> **`step-0.1.md` §6.3/§6.4 is the authoritative resolution table.** Where this
> document and that table could be read as disagreeing, §6.4 wins, and this
> document is the defect. Read it before implementing anything in section 4
> (the rule constants), section 5 (error codes) or `modules/auth/hooks/`
> (endpoints, the session shape, CSRF header handling).

Two consequences are already folded into the design above, so no criterion or
state row hedges any more: sign-up lands on `/` already signed in (6.5, UI-20),
and a password maximum exists, so `validation.password.tooLong` is live (4, 7.2).

**One resolution is restated here, because it governs component choice on
almost every line above: the MUI major is v9** (`@mui/material` `^9.4.0`).
The three version-sensitive APIs in this spec are the v9 ones and are correct as
written: `Button` `loading` (3.1), `slotProps.htmlInput` (3.1), and
`cssVariables` + `colorSchemes` (section 10). There is no fallback path in this
spec: `LoadingButton`, `inputProps` and a
`useMediaQuery('(prefers-color-scheme: dark)')` theme are pre-v9 shapes and
must not be used. See
`shared-knowledge.md` D14 for the full v7 → v9 divergence table.

## 12. Acceptance criteria

Every criterion carries a **`UI-` prefix**, because `step-0.1.md` §8 numbers its
own criteria in an overlapping range and qa-frontend reads both documents. A
bare number is always the architect's; `UI-n` is always this document's, and
every cross-reference elsewhere in this file uses the prefixed form. **The
numbers UI-1 … UI-38 are unchanged from the reviewed draft** — only the prefix
is new, so references already written elsewhere still resolve. New criteria are
appended from UI-39.

**Sign-in**

- **UI-1** — `GET /signin` renders one `<h1>` reading "Sign in", a Username field, a Password field, a submit button and a link to `/signup`.
- **UI-2** — Username has `autocomplete="username"`, Password has `type="password"` and `autocomplete="current-password"`.
- **UI-3** — Username receives focus on mount.
- **UI-4** — Submitting with both fields empty sends **no** network request, marks both fields invalid with their `required` messages, and moves focus to the Username field.
- **UI-5** — Sign-in applies no length or charset validation: a one-character username submits.
- **UI-6** — Pressing Enter in either field submits the form.
- **UI-7** — While in flight, the submit button is disabled and reads "Signing in…", and both text fields are disabled.
- **UI-8** — A 401 shows exactly one error message, in a `role="alert"` container, reading the invalid-credentials copy; the Username value is preserved, the Password value is cleared, and neither field is marked `aria-invalid="true"`.
- **UI-9** — The invalid-credentials message is byte-identical whether the username exists or not, and the UI exposes no other signal (field state, wording, timing branch) that distinguishes the two.
- **UI-10** — A network failure shows the network copy; a 422 and a 500 each show the unexpected copy; in all three cases both entered values are preserved. No field error is derived from a 422 `details` payload (§5.3).
- **UI-11** — After a failed submit, focus is on the alert, and Tab from there reaches Username.
- **UI-12** — On success the user lands on `/` via a history *replace* (pressing Back does not return to `/signin`), and focus moves to the greeting element — which is the home page's `<h1>`: the heading and the focus target are the same element (§6.5).

**Sign-up**

- **UI-13** — `GET /signup` renders one `<h1>` reading "Create an account", the two fields, the submit button and a link to `/signin`.
- **UI-14** — Password has `autocomplete="new-password"`; there is no confirm-password field and no visibility toggle.
- **UI-15** — Both fields show their rule hint as helper text before any interaction, with the rule numbers coming from `modules/auth/validation.ts` (no number is hard-coded in the translation JSON).
- **UI-16** — An untouched field shows no validation error; blurring an edited invalid field shows one; typing in it clears it again.
- **UI-17** — Only one validation message per field is ever visible, and it replaces the hint rather than appearing beside it.
- **UI-18** — A client-side-invalid submit sends no request and focuses the first invalid field.
- **UI-19** — A 409 marks the Username field `aria-invalid="true"`, puts the taken-username copy in the helper text that the input's `aria-describedby` points to, keeps both entered values, focuses the Username field, and shows **no** form-level alert.
- **UI-20** — On success the user lands on `/` via a history *replace*, already signed in: no interstitial, no "account created" notice and no second trip through `/signin`.

**Home and shell**

- **UI-21** — An unauthenticated visitor requesting `/` ends on `/signin` with no error or warning message shown, and the app shell/AppBar never renders during the attempt.
- **UI-22** — While the session read is in flight, a progress indicator with an accessible name ("Loading…") is on screen and no AppBar is rendered.
- **UI-23** — An authenticated `/` renders the AppBar with the app title and a "Sign out" button, and the greeting "Welcome, &lt;username&gt;." — and nothing else: no cards, no lists, no placeholder or "coming soon" content.
- **UI-24** — The greeting shows the username returned by the session endpoint, interpolated through i18n.
- **UI-25** — The first tab stop on `/` is the Sign out button.
- **UI-26** — Signing out disables the button, shows its loading indicator, then lands on `/signin` via *replace*; navigating Back does not show the authenticated home page again.
- **UI-27** — A failed sign-out (403, 5xx, an unmapped code or a network failure — a **401 is the deliberate case**, `step-0.1.md` §6.3 R10: it runs the success handler, redirects and shows no alert) leaves the user signed in and shows the sign-out error copy in a `role="alert"` container at the top of the main container, above the greeting. The alert is rendered by **`HomeRoute`** into `AppShell`'s `children`, and it and the button's pending state come from **one** `useSignOut()` instance owned by `HomeRoute`: `SignOutButton` calls no mutation hook of its own (grep it for `useSignOut`), so the failure that renders the alert is the same one that cleared the button's loading state.
- **UI-28** — On a reload with a session the server no longer recognises (`GET /api/v1/users/me` answering 401 `SESSION_EXPIRED`), the user is redirected to `/signin` and the "Your session ended." warning shows; a first-time visitor to `/signin`, and a 401 `NOT_AUTHENTICATED`, never show that warning. Nothing in step 0.1 re-reads the session while a tab stays open, so a mount is the only trigger to simulate (§6.3).
- **UI-29** — A session read that fails with a network error or a 500 shows an error alert plus a "Try again" control, and does **not** redirect to `/signin`.
- **UI-30** — An authenticated user navigating to `/signin` or `/signup` is redirected to `/`.

**Cross-cutting**

- **UI-31** — Every visible string in all three screens resolves from `common`, `auth` or `home`; grepping the components under `modules/auth` and `modules/home` (which includes `AppShell.tsx`) finds no user-facing string literal, and no key printed on screen shows as a raw key path.
- **UI-32** — `pnpm typecheck` fails if a `t()` key does not exist in the English resources.
- **UI-33** — No `@mui/icons-material` (or any other icon package) appears in `frontend/package.json`, and no icon is rendered on any of the three screens.
- **UI-34** — No hex, `rgb()`, or `hsl()` colour literal appears anywhere under `frontend/src`; `core/theme.ts` contains no `palette` overrides beyond enabling the dark scheme.
- **UI-35** — At 360 px width, none of the three screens scrolls horizontally, and the AppBar title truncates rather than wrapping or pushing the Sign out button off-screen.
- **UI-36** — All three screens render correctly under both `prefers-color-scheme: light` and `dark`, with the page background following the scheme (proof that `CssBaseline` is inside `ThemeProvider`).
- **UI-37** — Every state distinction in section 6 is legible with colour removed (grayscale screenshot): each state carries text.
- **UI-38** — The document title differs per route and never contains the framework default.

**Added after the step-0.1 spec review**

- **UI-39** — On a cold load of `/signin` or `/signup` with the session read in flight, `RequireAnonymous` renders the same full-viewport progress indicator as `RequireAuth` and **no** form: no Username field is in the document, so nothing takes `autoFocus` before the session answer arrives (§6.4).
- **UI-40** — `AppShell` lives at `frontend/src/modules/home/components/AppShell.tsx`; `frontend/src/components/` does not exist or is empty.
- **UI-41** — `AppShell` imports nothing from `modules/auth` and calls no data or mutation hook (grep its imports), so its only inputs are `title`, `action` and `children`.
- **UI-42** — Each of the three screens has exactly one `<h1>`, and it is inside the main content rather than the AppBar: on `/` the `<h1>` is the greeting, and the AppBar app title renders as a non-heading element.
- **UI-43** — `core/theme.ts` exports the theme and nothing else — no JSX and no provider; `main.tsx` renders `<ThemeProvider theme={theme} noSsr>` with no `defaultMode` prop (§10).
