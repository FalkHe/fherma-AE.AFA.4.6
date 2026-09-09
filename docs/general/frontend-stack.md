# Frontend stack

TypeScript. The conventions that go with the stack; layer boundaries and the
modular placement rules are in [architecture.md](architecture.md), per-module
detail in each `frontend/src/modules/<module>/README.md`. Where this document
and the code disagree, the code wins.

## Libraries

React 19 on Vite 8, Material UI 9 (+ Emotion, plain defaults — no design
system), TanStack Query 5 for all server state, React Router 8, react-i18next,
`openapi-fetch` as the single typed client and `openapi-typescript` as its
generator. Dev: vitest + jsdom + Testing Library, ESLint with
typescript-eslint. Exact versions live in `frontend/package.json`.

Three pins that must not be bumped casually:

- **TypeScript stays on 5.9, not 6.x or 7.x.** It is the only line satisfying
  every peer range in the tree: `typescript-eslint@8` requires `>=4.8.4
  <6.1.0`, `openapi-typescript@7` requires `^5.x`. Re-check both before moving.
- **pnpm's version is stated twice** — `packageManager` in `package.json` and
  `ARG PNPM_VERSION` in `docker/frontend.Dockerfile` — and the two must agree.
- **Script names are load-bearing**: the `Makefile` and the Dockerfile call
  `dev`, `lint`, `typecheck` and `test` by name.

## Conventions

### One HTTP client

`src/core/api/client.ts` is the only file that touches the network and the only
file under `src/` reading `import.meta.env`; no component or hook calls `fetch`
directly. It creates the `openapi-fetch` client from the generated `paths` type
with `credentials: "include"` (mandatory — cookie auth from another origin) and
owns the CSRF middleware implementing the header/module-memory scheme in
[architecture.md](architecture.md): `onResponse` stores an `X-CSRF-Token`
response header, `onRequest` attaches it to every non-`GET` request.

There is no `core/config.ts`: one environment variable with one reader is not an
abstraction. Under vitest `VITE_API_URL` is undefined, so paths are relative.

### Generated types never drift

After any backend change to a route or a request/response model, run
`make generate-api` (needs the stack up) and
`git diff --exit-code frontend/src/api/schema.d.ts`: a reported diff means the
committed types were stale, so commit the regenerated file. Watch for the
reverse case too — a locally declared stand-in type for a payload the backend
does not send yet. Delete the stand-in when the real field lands; never build
on one.

### Server state lives in TanStack Query

The query client comes from a `createQueryClient()` factory in
`src/core/queryClient.ts`. `retry: false` there is deliberate: an expected 401
must resolve immediately and the test suite must not wait on retries.

One hook per operation, in the owning module's `hooks/`. No server data in
`useState` and none in a context provider. The signed-in user is the query
keyed `["currentUser"]`, caching `{ user, sessionExpired }`; a 401 on it is an
expected state, not an error — it resolves to no user, and the server's error
`code`, not any client-side history, decides whether the sign-in screen shows
a session-expired warning. Mutations write their result into that cache key.

### Routing

Declarative `<Routes>` / `<Route>`. There is no `react-router-dom` package in
v8 — general APIs come from `react-router`, DOM-specific ones from
`react-router/dom`. No data routers, no loaders, no actions: authentication
state has exactly one source, the query cache.

`RequireAuth` is the only component that redirects to `/signin` on an expiry;
a deliberate sign-out navigates from its own mutation hook, which clears the
cache afterwards so the two cannot both fire.

### Material UI

`createTheme({ cssVariables: true, colorSchemes: { light: true, dark: true } })`
with `CssBaseline` **inside** `ThemeProvider`, otherwise the colour scheme never
reaches the page background. No palette, typography or component overrides and
no colour literal anywhere under `src/`: visual design is not being evaluated
yet.

v9 differences worth knowing, because most MUI material online is v5–v7:

- **Layout components no longer accept system props.** `<Box mt={2}>` and
  `<Stack alignItems="center">` are gone; use `sx`.
- **`Grid` takes `size`.** `<Grid size={{ xs: 12, sm: 6 }}>`, not `xs={12}`;
  `item` and `GridLegacy` are removed.
- **`<Button loading>`** is built in — no `LoadingButton`, no `@mui/lab`.
- **`slotProps={{ htmlInput: … }}`** replaces `inputProps`.
- **`colorSchemes` + `cssVariables`** replace a
  `useMediaQuery("(prefers-color-scheme: dark)")` theme.

### i18n

Single language `en`, no detector, no HTTP backend, no switcher until a second
language exists. **One namespace per frontend module, plus `common`**, with
`defaultNS = "common"`; other namespaces are addressed explicitly
(`t("auth:signIn.title")` via `useTranslation("auth")`). Setup and locale JSON
live under `src/core/i18n/`, where `CustomTypeOptions` makes keys
compile-checked — `pnpm typecheck` fails on a key that does not exist.

**Every user-facing string goes through a key**; a literal in a component is a
defect. Keys are dot-paths of camelCase segments, at most three deep. Numbers
in copy are interpolated from the owning module's constants, never written into
the JSON. Server error codes map to keys with a `common:errors.unexpected`
fallback; the server's English `message` is never displayed.

### Accessibility baseline

Real `<form>` elements that submit on Enter, a visible label on every input,
`autoComplete` on credential fields (`username`, `current-password`,
`new-password`), and `role="alert"` on anything announcing a failure.

## Provider composition

`src/main.tsx` holds the whole provider stack and nothing else. `src/App.tsx`
holds `<Routes>` and nothing else — no provider, no router, no layout.
Nesting, outermost first:

`StrictMode` → `ThemeProvider theme noSsr` (with `CssBaseline` as its first
child) → `I18nextProvider i18n` → `QueryClientProvider` (one
`createQueryClient()` at module scope) → `BrowserRouter` (from
`react-router/dom`) → `<App />`.

Theme outermost so `CssBaseline` covers everything; the router innermost so a
test can render `<App />` under a `MemoryRouter` instead — a nested router
throws, which is why `App.tsx` must stay router-free. `noSsr` suppresses the
second render pass `ThemeProvider` performs to guard SSR hydration when two
colour schemes are present: useless in a Vite SPA, and it costs a dark-mode
flicker.

## Vite and Vitest configuration

`vite.config.ts` is a **plain object** `defineConfig({...})`, not a function, so
`vitest.config.ts` can `mergeConfig` it and add its `test` block; `globals:
false` there means vitest APIs are imported explicitly in every test file.

Two `server` settings are not free choices: `host: "0.0.0.0"` is required for
the published container port to reach the dev server, and watch polling is
required because bind mounts do not propagate inotify events reliably
(`compose.yaml` sets `VITE_SERVER_USE_POLLING=true`).

## Test arrangement

Shared helpers live in `src/test/` and are **owned by qa-frontend**, whose
suites are their only consumer; the implementing agent creates no file there
and only points `setupFiles` at `./src/test/setup.ts`. Three constraints
survive that boundary:

- **One fetch dispatcher, installed at startup and never replaced.**
  `openapi-fetch`'s `createClient` captures `globalThis.fetch` when
  `core/api/client.ts` is evaluated, so the dispatcher goes into the setup
  file, which runs before any test module imports the client. Stubbing means
  re-registering routes on that one dispatcher.
- **An unstubbed request throws** — a missing stub must be a loud failure, not
  a silent network error the component renders as an offline message.
- **Requests are relative**, since `VITE_API_URL` is undefined under vitest.

A render helper supplies the same providers as `main.tsx`, with a **fresh**
`createQueryClient()` per test and a `MemoryRouter` in place of
`BrowserRouter`.

Test authorship and execution, plus browser acceptance, belong to the
`qa-frontend` agent; dev agents run only `pnpm lint`, `pnpm typecheck` and
`pnpm build`. Commands are listed in `.claude/CLAUDE.md`.
