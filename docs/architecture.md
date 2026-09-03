# Architecture

## Repository

Single monorepo:

```text
/
├── backend/  # Python backend code
│   ├── alembic/              # DB migrations
│   ├── app/
│   │   ├── api/
│   │   │   ├── endpoints/    # HTTP routes
│   │   │   └── schemas/      # request/response models
│   │   ├── cli/              # Typer commands
│   │   ├── db/
│   │   │   └── models/       # SQLAlchemy models
│   │   ├── llm/
│   │   │   ├── agents/       # AI agents & tools
│   │   │   └── prompts/      # versioned prompt templates
│   │   └── services/         # service layer
│   ├── pyproject.toml
│   └── ...
├── frontend/                 # React frontend code
│   ├── package.json
│   └── ...
├── docs/                     # project documentation & AI context
├── docker/                   # docker build
├── compose.yaml
└── README.md
```

---

# Backend Structure

Thin HTTP layer over a service layer:

```text
FastAPI route → service → SQLAlchemy → PostgreSQL
```

- Typical services: `ProductService`, `ChatService`, `DocumentService`, `EmbeddingService`, `UserService`. Services own transaction boundaries.
- FastAPI `Depends()` for dependency injection; no external DI container.
- No mandatory repository class per model — extract query objects only where they add clear value.

---

# API Design

Normal resources use JSON:API 1.1 (`/api/products`, `/api/documents`, `/api/chats`, `/api/chat-messages`, `/api/operations`), implemented as a small internal layer rather than a third-party framework. Special-purpose endpoints (`/auth/*`, `/uploads`, `/api/events`) stay plain where JSON:API would add complexity.

Conventions: page-number pagination (default page size 100), explicit sortable fields / filters / includes per resource, camelCase attributes, UTC ISO-8601 timestamps, no `/v1` prefix initially.

---

# Database / Persistence

PostgreSQL is the single source of truth: users, sessions, business entities, chat history, operation/job state, normalized document Markdown, chunks, embeddings, full-text search data.

SQLAlchemy ORM; explicit SQL where clearer. ULIDs as entity IDs.

---

# Authentication

Local username/password only — no email flows, no OAuth.

- Usernames: case-insensitively unique, changeable.
- Roles `user` and `admin`; admin assignment and password reset via CLI.
- Sessions: opaque tokens in PostgreSQL; "remember me" supported; no session-management UI.
- Cookies: `HttpOnly`, `Secure` in production, `SameSite=Lax`. CSRF protection on cookie-authenticated writes.

---

# Background Jobs

Taskiq with **Redis as broker** for work that must survive browser disconnects: chat response generation, ingestion, embedding (re)generation, long agent workflows.

Application-visible operation state (`queued/running/succeeded/failed`, progress, status message) lives in PostgreSQL. Taskiq Admin is dev-only visibility.

Transient failures retry with exponential backoff; deterministic/user-input failures do not. No transactional outbox, no scheduler; job cancellation can come later.

---

# Chat / Realtime

LLM tokens are not streamed. Chat mimics a natural conversation:

```text
customer message → seen → typing... → completed assistant message
```

A chat response may run as a Taskiq job. The completed message is persisted first, then the frontend is notified.

One SSE connection per logged-in SPA, carrying only small notifications (`chat.message.created`, `operation.updated`, `document.updated`, `product.updated`). The client then refetches through the normal API. Workers reach FastAPI via PostgreSQL LISTEN/NOTIFY. A lost notification loses no data — PostgreSQL holds the truth.

No WebSocket infrastructure.

---

# LLM / Agent Architecture

OpenRouter is the model gateway; LangChain is the default abstraction. Use LangGraph only when a workflow actually requires it.

**Resumability = persistence.** A user can stop today and continue tomorrow because every message and extracted preference lives in PostgreSQL; reopening a chat rebuilds the LLM context from history. No LangGraph checkpoint database — that would persist agent-internal state mid-run, which we don't need: an interrupted job simply reruns from the last user message.

Autonomous agents have configurable maximum steps and runtime. Prefer OpenRouter provider routing/fallback over app-level failover.

## Tool Boundaries

```text
agent tool → application service → database / external API
```

Read tools may run autonomously; write tools stay explicitly permissioned. MCP tools and native Python tools coexist behind the same agent interface.

---

# Prompt Management

Prompts are version-controlled Markdown files under `backend/app/llm/prompts/` with Jinja-style placeholders (`{{ customer.name }}`). Missing variables fail explicitly. No database prompt editor.

---

# AI Observability

Langfuse is **optional** and pluggable: one LangChain callback handler, enabled via config, so it can be added later without code changes. The application database never stores full traces, token usage, or cost data — that belongs to Langfuse when enabled.

---

# Ingestion (Web Search + Fetch)

Product research is search-then-fetch, not recursive crawling:

```text
query ("Suzuki GSR 600")
    ↓
web search API (provider via .env)
    ↓
fetch top ~5 results (HTTPX)
    ↓
optionally follow 1–3 in-page links if needed
    ↓
main-text extraction (trafilatura for HTML, Docling for PDF)
    ↓
normalized Markdown → chunks → embeddings
```

Original source documents are retained permanently. Admin-only uploads run through the same pipeline; declared filename/MIME type is trusted initially. Upload limits are high but finite and configurable.

Browser rendering is added later only if JS-heavy sites require it.

---

# RAG

English-only initially. Simple structural/recursive chunking (no semantic/LLM chunking).

Chunks preserve provenance where available: `sourceDocumentId`, `sourceUrl`, `sourceTitle`, `headingPath`, `pageNumber`, `sequence`. The UI shows provenance (titles, URLs) without promising exact quote-level citations, since sources are normalized to Markdown.

Hybrid retrieval with metadata filtering:

```text
PostgreSQL full-text search + pgvector cosine similarity + RRF
```

**Embeddings via OpenRouter.** The embedding model is configured in `.env` and stored alongside each embedding (model + dimensions). Because the configured model may change, a CLI command re-embeds everything as a background job.

---

# Images

Pillow generates the required image variants at ingest time; variants are served as static files. Product images are public. No dynamic image transformation service, no S3/MinIO.

---

# Frontend Architecture

React SPA. State split:

```text
server state            → TanStack Query (never copied into Redux/Zustand)
URL/search/filter state → React Router
local UI state          → React state
current user            → TanStack Query
```

React Router handles navigation, `user`/`admin` route guards, and URL-based filter state. Cached server data survives SPA navigation; SSE events invalidate/refetch the relevant TanStack Query data.

## API Contract

```text
FastAPI OpenAPI → openapi-typescript → openapi-fetch → TanStack Query hooks
```

Generated types are committed to Git. CLI command: `app openapi export`. No dedicated JSON:API client library.

## UI / Localization

Material UI (Material Design 2 acceptable). Responsive across desktop, tablet, smartphone. Theme modes `system | light | dark`, default `system`; only explicit user overrides are persisted.

English is the only language at first, but all user-facing strings go through an i18n layer (react-i18next) from the beginning, so adding a locale later is translation work, not refactoring. Dates/times formatted via browser `Intl`.

---

# Deployment / Docker

Development runs fully in Docker Compose (`uvicorn --reload`, Vite dev server).

Production uses one application image (Python runtime, FastAPI, Taskiq worker code, Typer CLI, prompts, compiled Vite frontend), reused by multiple containers:

- **Web container:** runs Alembic migrations on startup, then Uvicorn serving the API and the compiled SPA. Unknown non-API routes fall back to `index.html`.
- **Worker container:** Taskiq worker only; never runs migrations.

Uvicorn is exposed directly; reverse proxy/TLS out of scope.

## Compose Services

```text
Core:      app-web, app-worker, postgres, redis
Optional:  taskiq-admin (dev),
           langfuse-web, langfuse-worker, clickhouse, valkey, minio (Langfuse stack)
```

PostgreSQL may host separate databases (`application`, `taskiq_admin`, `langfuse`). Valkey/ClickHouse/MinIO belong to Langfuse only. The application itself uses Redis solely as the Taskiq broker.

---

# Health / Logging

`/health` = process alive. `/ready` = essential dependencies (PostgreSQL). A broker outage should not necessarily make the HTTP app unready.

Standard Python/Uvicorn logging to stdout. No centralized logging stack.

---

# Explicitly Out of Scope

```text
reverse proxy / TLS          rate limiting
database backup tooling      audit trail
strict password policy       user-facing session management
transactional outbox         scheduled ingestion
Prometheus metrics           Sentry
exhaustive test suites       application S3 storage
browser automation           advanced data-grid framework
```
