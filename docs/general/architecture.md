# Architecture

Current state. Module-level detail lives in [`../modules/`](../modules/).

## Repository

```text
/
├── backend/
│   ├── alembic/versions/      # migrations (single linear chain)
│   ├── app/
│   │   ├── api/
│   │   │   ├── endpoints/     # HTTP routes
│   │   │   ├── schemas/       # request/response models
│   │   │   ├── deps.py        # current_user / current_admin / csrf_protect
│   │   │   └── jsonapi.py     # the internal JSON:API layer
│   │   ├── cli/               # Typer commands (15 sub-apps)
│   │   ├── core/              # settings
│   │   ├── db/models/         # SQLAlchemy models
│   │   ├── jobs/              # Taskiq broker + tasks
│   │   ├── llm/
│   │   │   ├── agents/        # advisor loop + tools
│   │   │   └── prompts/       # versioned Markdown prompts
│   │   └── services/          # service layer
│   ├── scripts/               # demo_conversation.py
│   └── tests/
├── frontend/src/              # React SPA (routes/, components/, hooks/, api/, locales/)
├── docs/
├── docker/                    # backend.Dockerfile, frontend.Dockerfile, entrypoint-web.sh
├── compose.yaml               # + compose.langfuse.yaml
└── Makefile
```

## Backend structure

```text
FastAPI route → service → SQLAlchemy → PostgreSQL
```

- **Services are modules of functions**, not classes (`product_service`,
  `chat_service`, `catalogue_search_service`, …). Services own transaction
  boundaries; every public service function commits.
- FastAPI `Depends()` for injection; no DI container.
- **No ORM relationships anywhere** — foreign keys plus explicit service-level
  lookups (the `get_specs` pattern). This keeps async loading predictable.
- No repository class per model.
- After any write, a route must `await session.refresh(row)` before serialising
  (server-side `onupdate` otherwise raises `MissingGreenlet`).

## API design

Normal resources use JSON:API 1.1 over plain `application/json` (no content
negotiation), implemented as a small internal layer rather than a third-party
framework:

`/api/products` · `/api/documents` · `/api/product-images` · `/api/operations` ·
`/api/manufacturers` · `/api/catalogue-models` · `/api/chats` ·
`/api/chat-messages`

Plain, non-JSON:API endpoints: `/auth/*`, `GET /api/events` (SSE), `/media/*`,
`/health`, `/ready`.

Conventions: camelCase attributes, UTC ISO-8601 timestamps, no `/v1` prefix,
`page[number]`/`page[size]` pagination (default and maximum both **100**),
`meta.totalCount`, default sort `-createdAt`. **No relationships, no
`included`, no general sortable-field machinery** — the include mechanism was
never needed, and the only resource with a sort vocabulary is
`catalogue-models`. Request envelopes are `extra="forbid"` at every level, which
is what rejects an attempt to PATCH a read-only attribute.

Errors are `{"errors":[{"status","code","detail"}]}` via `JsonApiError`. Codes
in use: `not-found` (404), `duplicate-model` (409), `response-pending` (409),
`invalid-transition` (422), `incomplete-identity` (422), `invalid-filter` /
`missing-filter` (400), `internal-error` (500). Body/query validation keeps
FastAPI's default 422 shape; auth and CSRF keep `{"detail": …}` 401/403.
Clients branch on status plus `code`, never on detail text.

## Database

PostgreSQL is the single source of truth: users, sessions, catalogue entities,
chat history, job state, normalized document Markdown, chunks, embeddings and
full-text search vectors. SQLAlchemy 2 async ORM, explicit SQL where clearer.

ULID `String(26)` primary keys, `TIMESTAMPTZ` in UTC, native PostgreSQL enums
with lowercase stored values. Slugs are separate unique columns. Migrations are
a single linear Alembic chain; the web container runs `alembic upgrade head` at
startup, the worker never migrates.

## Authentication

Local username/password only — no email flows, no OAuth.

- Usernames: 3–32 chars `^[a-z0-9_.-]+$`, lowercased, unique. **Not
  changeable** — no code path exists.
- Roles `user` and `admin`; admin assignment and password reset via CLI
  (`app users set-role`, `app users reset-password`).
- Sessions: opaque tokens, sha256-hashed in PostgreSQL; TTL 24 h, or 30 days
  with "remember me"; no sliding renewal, no session-management UI.
- Cookies: `session` (HttpOnly) + `csrf_token` (readable), `SameSite=Lax`,
  `Secure` in production. CSRF double-submit on every cookie-authenticated
  write.
- Password hashing is Argon2 via pwdlib; a dummy hash keeps login timing flat
  for unknown usernames.

Details: [`security.md`](security.md).

## Background jobs

Taskiq with **Redis as the broker** for work that must survive browser
disconnects: ingestion, chat response generation, embedding rebuilds.

Application-visible job state lives in PostgreSQL (`operations`:
`queued/running/succeeded/failed`, `progress`, `message`, `error`); Taskiq has
**no result backend**, so task return values are never read. Only ids cross the
process boundary.

`SmartRetryMiddleware` retries **only** `TransientJobError` — 3 attempts,
delay × attempt with jitter, capped at 60 s (multiplicative, not exponential).
Deterministic and user-input failures never retry. No outbox, no scheduler, no
job cancellation. Exhausted retries are not reaped.

Task names: `ingestion.run`, `chat.respond`, `embeddings.rebuild`, `demo.ping`.
**The worker does not hot-reload** — restart it after code changes.

## Chat / realtime

LLM tokens are not streamed. A turn reads as a conversation:

```text
customer message → seen → typing… → completed assistant message
```

A chat response **always** runs as the `chat.respond` job; the completed message
is persisted first, then the frontend is notified. The advisor speaks first: the
greeting turn is enqueued by `POST /api/chats`.

One SSE connection per signed-in SPA carries only small id-bearing
notifications — `chat.message.created`, `operation.updated`, `product.updated`,
`document.updated` — and the client refetches through the normal API. Workers
reach FastAPI through PostgreSQL `LISTEN/NOTIFY` on a single channel
(`app_events`), so events fan out to every API worker; an in-process bus would
not. Payloads are ≤ 1 KB and carry ids only. State is committed *before* the
notify, so a lost notification loses no data.

No WebSockets, no polling anywhere.

## LLM / agent architecture

OpenRouter is the only model gateway, reached through LangChain. **LangGraph is
not used**: the advisor is a hand-rolled `bind_tools` loop with a step budget
and a wall-clock timeout.

**Resumability is persistence.** Every message and preference lives in
PostgreSQL, so reopening a chat rebuilds the context from history. There is no
checkpointer — an interrupted job simply reruns from the last user message.

Two models are configured separately: `ADVISOR_MODEL` for the consultation,
`CHAT_MODEL` for utility work (spec extraction, query translation). Model ids
are `.env` values and are never hardcoded or asserted in tests.

### Tool boundaries

```text
agent tool → application service → database / external API
```

Tools contain no SQL. All eight are native Python `ToolSpec`s — **there are no
MCP tools**. Five are reads; three are writes (`record_preference`,
`flag_unknown_bike`, `present_recommendations`) and run **autonomously** as
deliberately permitted low-risk writes. `flag_unknown_bike` is consent-gated by
the *prompt*, not by a permission mechanism. Any further write tool needs an
owner decision.

Details: [`../modules/retrieval-advisor.md`](../modules/retrieval-advisor.md).

## Prompt management

Version-controlled Markdown under `backend/app/llm/prompts/` with Jinja
placeholders, rendered under `StrictUndefined` so a missing variable raises
rather than leaving a hole. No database prompt editor.

## RAG

English-only. Structural chunking only (no semantic or LLM chunking).

Chunks carry `source_document_id`, `motorbike_id`, `sequence`, `heading_path`
and `page_number`; the URL and title live on `source_documents` and are joined
in on retrieval. The UI shows provenance (titles, URLs) without promising
quote-level citation, because sources are normalized to Markdown.

Hybrid retrieval with metadata filtering:

```text
PostgreSQL full-text search + pgvector cosine similarity + RRF
```

Embeddings go through OpenRouter; the model and dimensions are stored alongside
every vector, and a CLI command re-embeds everything as a background job when
the configured model changes.

## Images

Pillow writes three WebP variants at ingest time (320/640/1280), served as
static files from `/media`. **The `/media` mount is unauthenticated** — product
images are public by design. No dynamic image service, no S3/MinIO. Variant
paths are derived, never stored.

## Frontend architecture

React SPA. State split:

```text
server state            → TanStack Query (never copied into Redux/Zustand)
URL/search/filter state → React Router
local UI state          → React state
current user            → TanStack Query (["auth","me"])
```

React Router v7 (`react-router`, not `react-router-dom`) owns navigation,
`RequireAuth`/`RequireAdmin` guards and URL-based filter state. SSE events
invalidate the relevant queries. The **only** optimistic update in the app is
the outgoing chat message.

Route guards are UX only — the backend `current_admin` dependency is the real
boundary.

### API contract

```text
FastAPI OpenAPI → openapi-typescript → openapi-fetch → TanStack Query hooks
```

Generated types (`frontend/src/api/schema.d.ts`) are committed. Regenerate with
`make generate-api`; keeping it in step is a review item (see the
`qa-checklist` skill). Envelope unwrapping happens only in hooks.

### UI / localization

Material UI (Material Design 2). Responsive desktop→mobile. Theme modes
`system | light | dark`, default `system`, persisted by MUI under the `mui-mode`
localStorage key. Icons are Material Symbols ligatures via `<Icon>`
(`@mui/icons-material` is deliberately not a dependency).

English is the only locale, but every user-facing string goes through
react-i18next with compile-checked keys, so adding a language is translation
work. Dates and numbers use browser `Intl`. Operation `message`/`error` strings
are rendered verbatim from the backend — a deliberate i18n exemption.

## Deployment

Development runs fully in Docker Compose: `uvicorn --reload` (web), Taskiq
worker, Vite dev server.

```text
compose.yaml:          app-web, app-worker, frontend, postgres (pgvector/pg16), redis
                       app-cli, node-cli          (profile "cli", one-off runners)
compose.langfuse.yaml: langfuse-web, langfuse-worker, langfuse-postgres,
                       clickhouse, valkey, minio  (opt-in via COMPOSE_FILE)
```

The application uses Redis solely as the Taskiq broker. Langfuse brings its own
PostgreSQL container; ClickHouse/Valkey/MinIO belong to Langfuse only.

`docker/backend.Dockerfile` builds one image carrying the API, the worker code
and the Typer CLI; `docker/entrypoint-web.sh` runs migrations then Uvicorn, and
the worker container never migrates. A single-image production deployment that
also serves the compiled SPA is the intended shape but is **not built**: the
backend mounts only `/media`, there is no `index.html` fallback, and the
frontend ships as its own container. Reverse proxy and TLS are out of scope.

## Health / logging

`/health` = process alive. `/ready` = PostgreSQL reachable only — a broker
outage does not make the HTTP app unready. Standard Python/Uvicorn logging to
stdout; no centralized logging stack. `/docs` is exposed in `development` only.

## Explicitly out of scope

```text
reverse proxy / TLS          rate limiting
database backup tooling      audit trail
strict password policy       user-facing session management
transactional outbox         scheduled ingestion
Prometheus metrics           Sentry
exhaustive test suites       application S3 storage
browser automation           advanced data-grid framework
document uploads             PDF sources
```
