# Architecture

How the system is put together: the layer boundaries, the modular layout and
its rules, the wire convention, the request lifecycle, and the session/CSRF
flow.

Current state: scaffolding. The trees, the wire convention and authentication
exist; the game agent does not. Where this document and the code disagree, the
code wins.

## The three domain layers

The project separates three concerns, and this separation is architectural,
not stylistic:

- **Content** — campaigns, adventures, scenes and monster stat blocks as
  structured JSON. Structured lookups read JSON; they do not go through RAG.
- **Reasoning** — the LLM agent decides how a scene plays out.
- **Mechanics** — deterministic code: dice, hit points, state validation. The
  LLM never fakes a roll and never edits state directly; it calls a tool.

Only the SRD rules text is retrieved with RAG. None of these layers is built
yet; the boundary is stated here so nothing is built across it later.

## Deployment shape

```
browser ──► frontend (Vite dev server, :5173)
   │
   └──────► app-web (uvicorn, :8000) ──► postgres (pgvector, :5432)
```

`app-web` runs `alembic upgrade head` and then uvicorn, from
`docker/entrypoint-web.sh`. `app-cli` and `node-cli` are one-off containers
behind the Compose `cli` profile; they reuse the same images and are how
`make test` and `make lint` run without a host toolchain.

There is **no background job runner and no Redis.** Every operation is
request-scoped or a Typer CLI one-off. Anything that would once have been a
queued job is one of those two.

Optional Langfuse tracing lives in `compose.langfuse.yaml` and is enabled per
checkout via `COMPOSE_FILE`; without it the application behaves identically
with tracing off.

## Code layout — modular by domain

Both trees are organised by **module**, not by technical layer. A module owns
its models, schemas, routes and service; a reader can delete a module without
hunting through six shared directories.

```
backend/app/
├── main.py               # create_app() factory
├── cli.py                # Typer entry point, console script `app`
├── core/                 # settings, logging, db session, error envelope, security primitives
├── api/v1/router.py      # combines the modular routers, nothing else
└── modules/
    └── <module>/         # models.py schemas.py routes.py service.py
backend/tests/
└── <module>/             # mirrors modules/ one-to-one
```

```
frontend/src/
├── core/                 # theme, api client, i18n setup, query client
├── components/           # shared UI, promoted once two modules render it
├── api/                  # generated artefacts only (schema.d.ts)
└── modules/
    └── <module>/         # components/ hooks/ routes/
```

### The rules

- A shared **helper or component** earns its place in `core/` or
  `components/` only once a **second** module actually calls it, and only if
  it imports nothing from any of them; one caller means it lives in that
  caller's module and is promoted later. The per-app singletons `core/` exists
  for — the HTTP client, the query-client factory, the theme, the i18n
  instance — are placed architecturally and may have one importer.
- `app/api/v1/router.py` wires routers together and contains no logic.
- One module does not import another module's internals. Cross-module use goes
  through the other module's `service.py` functions or its `models.py` — which
  are that module's public surface — and is stated explicitly in the step
  spec. `auth` calling `users.service.verify_credentials` is such a case.
- Backend services are **modules of functions**, not classes. There are no
  repository classes and no ORM relationships: a query is a query.
- Services own the transaction boundary. `get_db_session` yields a session and
  rolls back on exception; it never commits. Mutating service functions call
  `await db.commit()` themselves. Routes contain no `commit`, no `add`, no
  `execute`.
- `frontend/src/api/schema.d.ts` is generated from the backend's OpenAPI
  schema and committed. It is never hand-edited, and no frontend type is ever
  hand-written as a stand-in for a payload the backend does not send yet.

## Wire convention

Plain REST under `/api/v1`. Resource objects are returned directly — there is
no document envelope, no JSON:API layer.

- **camelCase on the wire.** A shared Pydantic base in `app/core/schemas.py`
  sets `alias_generator=to_camel` and `populate_by_name=True`. FastAPI
  serialises response models by alias, so responses are camelCase without any
  mapping code, and requests accept camelCase.
- **One error envelope.** Every non-2xx response from the application has the
  body

  ```json
  { "error": { "code": "USERNAME_TAKEN", "message": "…", "details": null } }
  ```

  `code` is a stable domain string, `message` is English and server-side only,
  `details` is `null` or a JSON object. The frontend never displays `message`:
  it maps `code` to an i18n key with a fallback.
- **Domain codes, not HTTP codes, carry meaning.** Two failures that share a
  status get different codes (`NOT_AUTHENTICATED` vs `SESSION_EXPIRED` vs
  `INVALID_CREDENTIALS`, all 401), and two failures that must be
  indistinguishable share one (unknown username and wrong password are both
  `INVALID_CREDENTIALS`).
- **The catch-all.** An unhandled exception is logged with its traceback and
  answered with `500 INTERNAL_ERROR` and a fixed message. Nothing about the
  exception reaches the client.
- Each route declares its failure `responses=` explicitly, so every status the
  client can receive is in the OpenAPI schema and therefore in the generated
  TypeScript types.

## Request lifecycle

1. **CORS.** `CORSMiddleware` with exactly one allowed origin (the SPA's,
   from the `FRONTEND_ORIGIN` setting — never `*`),
   `allow_credentials=True`, and `X-CSRF-Token` in both `allow_headers` and
   `expose_headers`.
2. **Routing.** `create_app()` mounts `app/api/v1/router.py` at `/api/v1`;
   that router includes each module's router under its own prefix and tag.
3. **Validation.** Pydantic validates the body. A failure never reaches the
   route: the `RequestValidationError` handler answers
   `422 VALIDATION_ERROR` with `details.fields` carrying the encoded
   Pydantic errors.
4. **Authentication.** Protected routes depend on `require_auth`, which reads
   the `session` cookie and yields an `AuthContext` holding the user and the
   session row. That is **two** queries — the session row, then the user by
   id — because there are no ORM relationships, so a session row has no
   `.user`.
5. **CSRF.** Mutating protected routes depend on `require_csrf`, which
   compares the `X-CSRF-Token` request header against the session row in
   constant time.
6. **Service call.** The route translates the validated request into a call to
   its module's service, which owns the query and the commit.
7. **Serialisation.** The route returns a Pydantic response model; FastAPI
   serialises it by alias.
8. **Errors.** A service raises `ApiError(code, status, details)`; a single
   handler renders it into the envelope, and that handler is also what clears
   the `session` cookie on `SESSION_EXPIRED` — a dependency that raises has its
   injected `Response` discarded, so it cannot clear the cookie itself. Starlette's `HTTPException` (404,
   405) and any other exception (500) are rendered by the same envelope.

## Session and CSRF flow

Authentication is server-side sessions. There are no JWTs and nothing is
signed.

```
register / sign-in
  ├─ verify or create the user (Argon2)
  ├─ token      = secrets.token_urlsafe(32)          → Set-Cookie: session=<token>  (HttpOnly)
  ├─ csrf_token = secrets.token_urlsafe(32)          → X-CSRF-Token: <csrf_token>   (response header)
  └─ INSERT sessions(user_id, token_hash=sha256(token), csrf_token, expires_at)

any authenticated request
  ├─ read the `session` cookie
  ├─ SELECT … WHERE token_hash = sha256(cookie) AND expires_at > now()
  ├─ missing cookie          → 401 NOT_AUTHENTICATED
  ├─ unknown or expired row  → 401 SESSION_EXPIRED (the ApiError handler clears the cookie)
  └─ mutation? compare X-CSRF-Token against sessions.csrf_token → 403 CSRF_TOKEN_INVALID

GET /users/me
  └─ re-issues X-CSRF-Token, so the SPA recovers the token after a page reload

sign-out
  └─ DELETE the session row, clear the cookie
```

Routes and dependencies never construct a `Response`: they take
`response: Response`, set cookies and headers on it, and return the response
model or `None`. FastAPI merges those headers into the real response, including
a bodiless `204`.

### Why it is shaped this way

- **Opaque token, hashed at rest.** The database stores
  `sha256(token).hexdigest()`. A database dump therefore yields no usable
  session cookies. Revocation is a `DELETE`, which a JWT cannot offer without
  reintroducing server state.
- **`HttpOnly` cookie for the credential.** Script cannot read it, so an XSS
  bug cannot exfiltrate the session.
- **Synchroniser token in a header for CSRF.** The token is never in a cookie
  and never in a response body. A cross-site page cannot read a
  CORS-protected response header, so it cannot learn the token; and because
  the header is compared against the database row rather than a second cookie,
  the double-submit cookie-injection weakness does not apply.
- **The SPA keeps the token in module memory only** — not in `localStorage`,
  not in a cookie, not in React state — and re-acquires it from
  `GET /users/me` on every page load.
- **`SameSite=Lax` is correct across ports.** SameSite compares sites and the
  port is not part of a site, so `localhost:5173` → `localhost:8000` is
  same-site. It is nevertheless cross-**origin**, which is why CORS and
  `credentials: "include"` are both mandatory.
- **`Secure` only in production.** The development stack is plain HTTP; the
  flag is driven by the `ENVIRONMENT` setting.
- **One persona.** There is a single implicit `user` role and no role column.
  Authorisation is ownership: a record belongs to a user id.

## Frontend data flow

- **One HTTP client.** `src/core/api/client.ts` creates the `openapi-fetch`
  client from the generated `paths` type, with `credentials: "include"`, and
  owns the CSRF middleware: it stores the token from any response that carries
  it and attaches it to every non-`GET` request. Nothing else in the frontend
  calls `fetch`.
- **Server state lives in TanStack Query, not in React state.** The signed-in
  user is the query keyed `["currentUser"]`, caching `{ user, sessionExpired }`;
  a 401 on that query is an expected state and not an error — it resolves to no
  user, and `sessionExpired` records whether the server said `SESSION_EXPIRED`
  or `NOT_AUTHENTICATED`. Mutations write the result into that cache key.
- **Routing is declarative** (`<Routes>` / `<Route>`), with no loaders or
  actions, so authentication state has exactly one source.
- **Every user-facing string is an i18n key.** Components contain no literal
  copy.

## Environment and settings

Settings are a single `pydantic-settings` class in `app/core/settings.py`,
reached through an `@lru_cache`d `get_settings()`. Only what the code reads is
declared; extra keys in `.env` are ignored, so `.env.dist` may document
variables a later phase will use.

`get_engine()` and `get_sessionmaker()` in `app/core/db.py` are `@lru_cache`d
and are called only from the request dependency — never at import time and
never from a lifespan handler. The cache is keyed process-wide rather than per
event loop, so an engine built outside the serving loop breaks async tests;
see `.claude/skills/qa-checklist/SKILL.md`.

Application logs go to **stderr**. Stdout is reserved for command output, so
`app openapi export > frontend/openapi.json` produces valid JSON.
