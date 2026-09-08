# Frontend stack

TypeScript. What is installed, how it is arranged, and the conventions that go
with it. Architecture and layer boundaries are in
[architecture.md](architecture.md).

## Libraries

| Library | Role |
|---|---|
| **React 19** | UI |
| **Vite 8** | Dev server and build |
| **Material UI 9** (`^9.4.0`, + Emotion 11) | Components. Plain defaults, no design system |
| **TanStack Query 5** | All server state |
| **React Router 8** | Declarative routing |
| **react-i18next 17** / **i18next 26** | Every user-facing string |
| **openapi-fetch** | The single typed HTTP client |
| **openapi-typescript** | Generates `src/api/schema.d.ts` from the OpenAPI schema |

Dev: **vitest 5**, **jsdom**, **@testing-library/react** (+ `/dom`,
`/jest-dom`, `/user-event`), **eslint 10** with **typescript-eslint 8**,
**eslint-plugin-react-hooks**, **eslint-plugin-react-refresh**.

Node 24 and **pnpm 11.17.0**, pinned by the `packageManager` field in
`package.json` and by `ARG PNPM_VERSION` in `docker/frontend.Dockerfile`.
Those two must agree. Install settings (`onlyBuiltDependencies`) live in
`pnpm-workspace.yaml`, which the Dockerfile copies before the source.

**TypeScript is pinned at 5.9, not 6.x or 7.x.** It is the only line that
satisfies every peer range in the tree: `typescript-eslint@8` requires
`>=4.8.4 <6.1.0` and `openapi-typescript@7` requires `^5.x`. Do not bump it
without re-checking both.

## Layout

```
frontend/
├── package.json  pnpm-lock.yaml  pnpm-workspace.yaml
├── tsconfig.json  tsconfig.app.json  tsconfig.node.json
├── vite.config.ts  vitest.config.ts  eslint.config.js
├── index.html
├── openapi.json              # exported from the backend; input to generate:api
└── src/
    ├── main.tsx  App.tsx
    ├── api/schema.d.ts       # GENERATED — never hand-edited
    ├── core/                 # theme, api client, i18n, query client
    ├── components/           # shared UI, promoted once two modules render it
    ├── modules/<module>/     # components/ hooks/ routes/
    └── test/                 # shared test helpers — owned by qa-frontend
```

`src/core/` holds the per-app singletons — the HTTP client, the query-client
factory, the theme, the i18n instance — plus any **helper** that two or more
modules actually use. A single-caller helper lives in its caller's module.
`src/api/` is the one directory outside that scheme: it holds generated
artefacts only, and it exists because the `Makefile` writes there.

`src/components/` is for UI that **two or more modules actually render while
itself knowing nothing about any of them**. Until that is true, a component
lives in its caller's module and is **promoted later, unchanged** — born in a
module, promoted on evidence. `AppShell.tsx` is the reference case for both
halves of that rule: its shape (`title` + an `action?: ReactNode` slot +
`children`, importing nothing from any module) is exactly what makes it
promotable, and yet in phase 0 it sits in `modules/home/components/` because
`HomeRoute` is its only caller — the route's own module fills the slot with the
auth module's `SignOutButton`. A component that reaches into a module's hooks
belongs in that module however many routes render it.

## Conventions

### One HTTP client

`src/core/api/client.ts` is the only file that touches the network. It creates
the `openapi-fetch` client from the generated `paths` type:

```ts
createClient<paths>({ baseUrl: import.meta.env.VITE_API_URL, credentials: "include" })
```

`credentials: "include"` is mandatory — the API authenticates with a cookie
and the SPA is on a different origin. The same file owns the CSRF middleware:
`onResponse` stores an `X-CSRF-Token` response header when one is present,
`onRequest` attaches the stored token to every non-`GET` request. The token
lives in module memory only — never in a cookie, `localStorage` or React
state — and is re-acquired from `GET /api/v1/users/me` on every page load.

No component or hook calls `fetch` directly.

### Generated types never drift

`src/api/schema.d.ts` is generated and committed. After any backend change to
a route or a request/response model:

```bash
make generate-api                       # needs the stack up
git diff --exit-code frontend/src/api/schema.d.ts
```

A reported diff means the committed types were stale — commit the regenerated
file. Watch for the reverse case too: a frontend type declared locally as a
stand-in for a payload the backend does not send yet. Delete the stand-in when
the real field lands; never build on one.

With host pnpm, `pnpm generate:api` regenerates from an existing
`frontend/openapi.json` without a running backend.

### Server state lives in TanStack Query

The query client comes from a `createQueryClient()` factory in
`src/core/queryClient.ts` with
`defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 30_000 } }`.
`retry: false` is deliberate: an expected 401 must resolve immediately and the
test suite must not wait on retries.

- One hook per operation, in the owning module's `hooks/`.
- The signed-in user is the query keyed `["currentUser"]`, caching
  `{ user, sessionExpired }`. A 401 on it is an expected state, not an error:
  it resolves to no user, and `sessionExpired` records whether the server said
  `SESSION_EXPIRED` (a cookie was sent and resolved to nothing) or
  `NOT_AUTHENTICATED` (no cookie). That code — not any client-side history —
  is what decides whether the sign-in screen shows a session-expired warning.
  Mutations write their result into that cache key.
- No server data in `useState` and none in a context provider.

### Routing

Declarative `<Routes>` / `<Route>` from `react-router`. There is no
`react-router-dom` package in v8 — general APIs come from `react-router` and
DOM-specific ones from `react-router/dom`. No data routers, no loaders, no
actions: authentication state has exactly one source, the query cache.

Route protection is a pair of components: `RequireAuth` renders a spinner
while the current-user query is pending, `<Navigate to="/signin" replace />`
(remembering the attempted location as router state `from`, plus
`reason: "sessionExpired"` when the server said so) when it resolves to no
user, a retryable error alert when it fails for a network or 5xx reason, and
its children otherwise. `RequireAnonymous` sends an authenticated visitor from
`/signin` or `/signup` back to `/`. **`RequireAuth` is the only component that
redirects to `/signin` on an expiry**; a deliberate sign-out navigates from its
own mutation hook, which clears the cache afterwards so the two cannot both
fire.

### Material UI

`createTheme({ cssVariables: true, colorSchemes: { light: true, dark: true } })`
plus `ThemeProvider` with `CssBaseline` **inside** it (otherwise the colour
scheme never reaches the page background) — mounted in `main.tsx` with the
rest of the provider stack, never in `App.tsx`. No palette, typography or component
overrides, no custom component library, no colour literal anywhere under
`src/` — visual design is not being evaluated yet. The two schemes are enabled
because it costs one line and makes the app follow the operating system; that
is not a design decision.

v9 differences worth knowing, because most MUI material online is v5–v7:

- **Layout components no longer accept system props.** `<Box mt={2}>` and
  `<Stack alignItems="center">` are gone; use `sx`.
- **`Grid` takes `size`.** `<Grid size={{ xs: 12, sm: 6 }}>`, not `xs={12}`;
  `item` and `GridLegacy` are removed.
- **`<Button loading>`** is built in — there is no `LoadingButton` and no
  `@mui/lab` dependency.
- **`slotProps={{ htmlInput: … }}`** replaces `inputProps`.
- **`colorSchemes` + `cssVariables`** replace a
  `useMediaQuery("(prefers-color-scheme: dark)")` theme.

### i18n

Single language `en`. **One namespace per frontend module, plus `common`**,
with `defaultNS = "common"`; other namespaces are addressed explicitly
(`t("auth:signIn.title")` via `useTranslation("auth")`).

```
src/core/i18n/index.ts                    # i18next.use(initReactI18next).init(...)
src/core/i18n/i18n.d.ts                   # CustomTypeOptions -> compile-checked keys
src/core/i18n/locales/en/{common,auth,home}.json
```

```ts
i18next.use(initReactI18next).init({
  resources, lng: "en", fallbackLng: "en", defaultNS: "common",
  interpolation: { escapeValue: false },
});
```

No language detector, no HTTP backend, no switcher until a second language
exists. **Every user-facing string goes through a key** — a literal in a
component is a defect, and `pnpm typecheck` fails on a key that does not
exist. Keys are dot-paths of camelCase segments, at most three deep. Numbers
in copy are interpolated from the owning module's constants, never written
into the JSON. Server error codes map to keys with an
`common:errors.unexpected` fallback; the server's English `message` is never
displayed.

### Accessibility baseline

Real `<form>` elements that submit on Enter, a visible label on every input,
`autoComplete` on credential fields (`username`, `current-password`,
`new-password`), and `role="alert"` on anything announcing a failure.

## Vite and Vitest configuration

`vite.config.ts` is a **plain object** `defineConfig({...})`, not a function,
so `vitest.config.ts` can `mergeConfig` it. It sets

```ts
server: {
  host: "0.0.0.0", port: 5173, strictPort: true,
  watch: { usePolling: process.env.VITE_SERVER_USE_POLLING === "true" },
}
```

`host: "0.0.0.0"` is required for the published container port to reach the
dev server; polling is required because bind mounts do not propagate inotify
events reliably (`compose.yaml` sets `VITE_SERVER_USE_POLLING=true`).

`vitest.config.ts` merges the Vite config and adds
`test: { environment: "jsdom", globals: false, setupFiles: ["./src/test/setup.ts"], include: ["src/**/*.test.{ts,tsx}"], css: false }`.
`globals: false` means vitest APIs are imported explicitly in every test file.

`VITE_API_URL` is read once, in `src/core/api/client.ts`, which is the only
file under `src/` that touches `import.meta.env`. There is no `core/config.ts`:
one variable with one reader is not an abstraction. Under vitest the variable
is undefined, so `baseUrl` is `undefined` and request paths are relative.

## Provider composition

`src/main.tsx` holds the whole provider stack and nothing else. `src/App.tsx`
holds `<Routes>` and nothing else — no provider, no router, no layout. Nesting,
outermost first:

`StrictMode` → `ThemeProvider theme noSsr` (with `CssBaseline` as its first
child) → `I18nextProvider i18n` → `QueryClientProvider` (one
`createQueryClient()` at module scope) → `BrowserRouter` (from
`react-router/dom`) → `<App />`.

`noSsr` suppresses the second render pass `ThemeProvider` performs to guard SSR
hydration when two colour schemes are present — useless in a Vite SPA, and it
costs a dark-mode flicker. Theme outermost so `CssBaseline` covers everything;
the router innermost so a test can render `<App />` under a `MemoryRouter`
instead. A nested router
throws, which is why `App.tsx` must stay router-free.

## Test arrangement

Shared helpers live in `src/test/` and are **owned by qa-frontend**, whose
suites are their only consumer; it chooses their signatures. The implementing
agent creates no file there and only points `vitest.config.ts`'s `setupFiles`
at `./src/test/setup.ts`. Three constraints survive that boundary:

- **One fetch dispatcher, installed at startup and never replaced.**
  `openapi-fetch`'s `createClient` captures `globalThis.fetch` when
  `core/api/client.ts` is evaluated, so the dispatcher goes into the setup
  file, which runs before any test module imports the client. Stubbing means
  re-registering routes on that one dispatcher.
- **An unstubbed request throws** — a missing stub must be a loud failure, not
  a silent network error the component renders as an offline message.
- **Requests are relative**: `VITE_API_URL` is undefined under vitest.

A render helper supplies the same providers as `main.tsx` (a **fresh**
`createQueryClient()` per test) with a `MemoryRouter` in place of
`BrowserRouter`.

## Tooling

```bash
# from frontend/, after `pnpm install`
pnpm dev            # Vite dev server
pnpm build          # tsc -b && vite build
pnpm lint           # ESLint
pnpm typecheck      # tsc -b --force
pnpm test           # Vitest, one shot
pnpm test:watch
pnpm generate:api   # openapi-typescript openapi.json -o src/api/schema.d.ts

# or, Docker-only, works with the stack down
make frontend-lint  make frontend-typecheck  make frontend-test
```

Script names are load-bearing: the `Makefile` and
`docker/frontend.Dockerfile` call `dev`, `lint`, `typecheck` and `test` by
name. Run `make build` after a dependency change so the `node-cli` image
stays fresh, and `make rebuild` to renew the `node_modules` volume in the
running stack.

Test authorship and execution, plus browser acceptance, belong to the
`qa-frontend` agent; dev agents run only `pnpm lint`, `pnpm typecheck` and
`pnpm build`.
