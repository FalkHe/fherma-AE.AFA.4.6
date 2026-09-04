# Motorcycle Buying Advisor

A conversational AI advisor that interviews a customer about their needs and
recommends motorcycle models, grounded in an internal curated database of
verified specifications and retrieved prose about how those bikes are
actually regarded — rather than an LLM's outdated training data or
marketing-biased public sources. This is the AE.AFA.4.6 Turing College
Sprint 4 project ("Stage 02"), continuing the AE.AFA.3.5 Sprint 3 project
("Stage 01"): a domain-specialised RAG chatbot built with LangChain,
advanced RAG techniques, tool calling, and a vector database.

## Current State

Functional prototype with Catalogue Ingestion and Customer AI Advisor to demonstrage Core Requirements of this Sprint.
CapStone might be polished frontend and Guided Ingestion Agent(s) in Admin UI. 

## Where to find the Core Requirements

**1. RAG implementation**
`backend/app/services/chunking.py`, `backend/app/llm/embeddings.py`,
`backend/app/services/retrieval_service.py`,
`backend/app/services/rag_pipeline_service.py`
Ingested pages are chunked heading-aware with provenance, embedded through
LangChain into a pgvector column, and retrieved by a single SQL statement
that fuses a full-text leg and a vector leg with Reciprocal Rank Fusion.
The pipeline service adds query translation on top and fuses across the
rewritten sub-queries.

**2. Tool calling (≥3 — eight registered)**
`backend/app/llm/agents/tools/`, loop in `backend/app/llm/agents/advisor.py`
`catalogue_search`, `spec_comparison`, `licence_fit_check`,
`cost_estimator`, `retrieve_bike_knowledge`, `record_preference`,
`flag_unknown_bike`, `present_recommendations`. The advisor loop binds them
via LangChain `bind_tools` and persists every executed call, so the UI can
render what the advisor actually did.

**3. Domain specialisation**
`backend/app/llm/prompts/` (`advisor_system.md`, `query_translation.md`),
`backend/app/llm/fencing.py`, `docs/general/project-vision.md`
Motorcycle buying advice: versioned domain prompts drive the interview and
turn an utterance into search queries plus hard spec filters. Retrieved
third-party text is sentinel-fenced before the model sees it, the domain's
main security measure against indirect prompt injection.

**4. LangChain over OpenRouter, errors, validation**
`backend/app/llm/models.py`, `backend/app/api/jsonapi.py`,
`backend/app/main.py`, `backend/app/api/schemas/`
`get_chat_model` is the single factory and points `ChatOpenRouter` at
OpenRouter (never `api.openai.com`). Errors leave as JSON:API envelopes with
stable domain codes behind a catch-all 500 handler; validation is
schema-level Pydantic — on the API surface *and* on every tool's `Args`.

**5. React UI with sources, tool results, progress**
`frontend/src/components/`: `MessageSources.tsx`, `ModelSources.tsx`,
`ToolResultBlock.tsx` (+ per-tool renderers, `RecommendationCard.tsx`),
`TypingIndicator.tsx`, `OperationProgress.tsx`, `LiveConnectionAlert.tsx`
Every assistant message carries its citations and its tool-call results;
chat turns and ingestion runs show live progress (SSE-fed) rather than
freezing.

### Optional (bonus) tasks implemented

| Task | Level | Where | What it does |
|---|---|---|---|
| Source citations in responses | Easy | `backend/app/services/retrieval_service.py`, `frontend/src/components/MessageSources.tsx`, `ModelSources.tsx` | Each retrieved chunk's provenance (URL, title, heading path) is persisted as `sources[]` on the assistant message and rendered as links under the answer. |
| Visualisation of the RAG process | Easy | `frontend/src/components/ToolResultBlock.tsx`, `backend/app/llm/agents/tools/retrieve_bike_knowledge.py` | The `retrieve_bike_knowledge` result shows the rewritten queries, derived spec filters and candidate model ids — the retrieval plan per turn, not just its output. |
| Prompt-injection protection | Medium | `backend/app/llm/fencing.py`, `frontend/src/components/UntrustedMarkdown.tsx` | Sentinel fencing plus lookalike-stripping on every untrusted string reaching the model (chunk text, preferences, translation context); markdown rendered with raw HTML off. Live-verified against a planted payload. |
| Authentication and personalisation | Medium | `backend/app/api/endpoints/auth.py`, `backend/app/services/user_service.py`, `session_service.py`, `backend/app/llm/agents/tools/record_preference.py` | Username/password auth with Argon2, server-side sessions, CSRF tokens and customer/admin roles; `record_preference` stores what the customer revealed and feeds it back into the prompt and retrieval. |
| Visualisation of tool call results | Medium | `frontend/src/components/ToolResult*.tsx`, `RecommendationCard.tsx` | Four tools get styled renderers and `present_recommendations` renders as cards; dispatch falls back to a generic key/value view so no call disappears. |
| Real-time knowledge-base updates | Medium | `backend/app/jobs/ingestion.py`, `backend/app/api/endpoints/events.py`, `frontend/src/components/OperationProgress.tsx` | An admin adds a model while the app runs; ingestion executes as a background job, streams progress over SSE, and approval republishes it to the customer catalogue with no restart. |
| Hybrid search | **Hard** | `backend/app/services/retrieval_service.py`, `rag_pipeline_service.py` | Full-text (GIN `tsvector`) and vector (HNSW pgvector) legs in one SQL statement, fused by Reciprocal Rank Fusion; a second RRF pass fuses across translated sub-queries. |

Partially implemented: conversation history (persisted and resumable at
`/consultations`, but no export), logging and monitoring (structured logging
plus optional Langfuse tracing via `compose.langfuse.yaml` — see
`backend/app/llm/models.py`; no per-turn grouping, no metrics), multi-model
support (`CHAT_MODEL` / `ADVISOR_MODEL` / `EMBEDDING_MODEL` are independent
settings, but no in-UI picker), automated KB updates (fully automated once
triggered, but the trigger is an admin action). `docs/general/decisions.md`
records what was deliberately not built, and `docs/general/security.md` the
known gaps.

## Quick start (for reviewers)

Everything runs in Docker. Make sure ports `5173` and `8000` are free on localhost. 
Use `make` or review `Makefile` for exact `docker`  commands.

### Startup

```bash
git clone git@github.com:TuringCollegeSubmissions/fherma-AE.AFA.4.6.git
cd fherma-AE.AFA.4.6
cp .env.dist .env   
```       
Add your `OPENROUTER_API_KEY` to .env.

```bash  
make up                    # starts API, worker, frontend, Postgres, Redis; migrates the DB
make snapshot-load         # restores a curated catalogue: rows, sources, images, embeddings
```

> **`make snapshot-load` cannot work in this checkout.** The snapshot lives in
> `backend/resources/catalogue-snapshot/`, which is absent from this repository
> and untracked in git — it was not carried over from the Stage-01 copy. Until
> it is restored, populate the catalogue with `app seed demo` instead (real
> ingestion: needs `OPENROUTER_API_KEY`, costs API calls, takes minutes per
> model). See `docs/modules/demo-data.md`.

Visit http://localhost:5173 for customer frontend

Retister with Userame and Password.

gain admin role
```bash
docker compose exec app-web app users set-role <username> admin
```
Visit http://localhost:5173/admin or use main nav to switch to Admin UI

to stop the stack
```bash
make down
```

## long version

1. **Clone the repository** and `cd` into it.

2. **Create `.env` from the template**: `cp .env.dist .env`. Then set
   `OPENROUTER_API_KEY` — **the advisor chat cannot answer without it**, because
   every conversation turn calls an LLM through OpenRouter. `TAVILY_API_KEY` is
   optional and only affects *new* ingestion (web search); leave it empty to
   review the app against the restored catalogue. No other key needs changing.

3. **Start the stack**: `make up`. The `app-web` container runs
   `alembic upgrade head` on boot, so the schema is ready without a separate
   command. Give it a few seconds; `make ps` shows the services and
   `docker compose logs -f app-web` shows why if one does not come up.

4. **Restore the catalogue**: `make snapshot-load`. This loads the committed
   demo catalogue in about fifteen seconds, with no API calls and no ingestion
   run: 208 entries — 53 of them reviewed and approved, so visible to customers
   and available to the advisor, the rest sitting in the admin backlog — with
   their source documents, their images **and their embeddings**. Without this
   step the app runs but the catalogue is empty, so there is nothing to browse
   and nothing for the advisor to recommend.

5. **Register and promote yourself to admin.** Open
   <http://localhost:5173>, register an account, then grant it the admin role
   (no HTTP endpoint does this, by design):

   ```bash
   docker compose exec app-web app users set-role <your-username> admin
   ```

   Sign out and back in so the new role is on your session.

6. **Use the app**:
   - Customer UI (browse the catalogue, start a consultation):
     <http://localhost:5173>
   - Admin UI (add a model, watch ingestion live, review and approve):
     <http://localhost:5173/admin>
   - Interactive API docs: <http://localhost:8000/docs>

`make down` stops everything. `docs/README.md` indexes the documentation —
start there for architecture and subsystem detail; the sections below cover
each step of the setup in full.

## Stack

- Backend: Python, FastAPI, Typer, SQLAlchemy 2 (async), Alembic, PostgreSQL
  (pgvector), Redis, Taskiq (background jobs), LangChain + OpenRouter (LLM and
  embeddings) — see `docs/general/backend-stack.md`.
- Frontend: TypeScript, React, Vite, Material UI, TanStack Query, React
  Router, react-i18next — see `docs/general/frontend-stack.md`.
- Architecture and conventions: `docs/general/architecture.md`.

## Prerequisites

- Docker and Docker Compose v2 (`docker compose`)
- [uv](https://docs.astral.sh/uv/) — for running the backend outside Docker
- Node.js 24 and [pnpm](https://pnpm.io/) 11.17.0 — for running the frontend
  outside Docker (pnpm version is pinned via the `packageManager` field in
  `frontend/package.json`)

Docker Compose (plus `make` for the shortcuts) is the only requirement — the
Makefile routes tests, lint, type checks, and API-client generation through
one-off CLI containers (`app-cli`, `node-cli` in `compose.yaml`), so no host
Python or Node toolchain is needed. uv and pnpm are only for optionally
running the apps or their checks directly on the host.

## First-run setup

1. Copy the environment template and adjust it if needed:

   ```bash
   cp .env.dist .env
   ```

   **This step is manual and must stay manual.** No agent or tooling in this
   repo creates `.env` automatically — `.env.dist` documents every key with a
   comment, and `.env` itself is git-ignored.

   Most keys have working defaults out of the box (`DATABASE_URL`,
   `REDIS_URL`, `ENVIRONMENT`, `LOG_LEVEL`, chunking/embedding sizes, fetch
   limits). Two are optional API keys that degrade gracefully when left
   empty, at the cost of reduced functionality:

   - `TAVILY_API_KEY` — without it, ingestion runs Wikipedia-only (no web
     search) and appends a warning instead of failing.
   - `OPENROUTER_API_KEY` — without it, the app still starts, but spec
     extraction and embedding generation skip with a warning instead of
     calling an LLM.

   Set both to use ingestion and the LLM features fully — see
   `docs/modules/ingestion.md`.

2. Start the stack:

   ```bash
   make up          # shorthand for: docker compose up -d
   ```

   A root `Makefile` wraps the common workflows — `make help` lists them all
   (`up`, `down`, `build`, `rebuild`, `logs`, `ps`, plus the test/lint
   targets described below). This starts `app-web` (API), `app-worker`
   (Taskiq background jobs — ingestion, chunking, embeddings), `frontend`,
   `postgres`, and `redis`.

   The `app-web` container runs `alembic upgrade head` before starting
   Uvicorn, so Postgres must be healthy first — Compose's `depends_on:
   condition: service_healthy` enforces that. `app-worker` never runs
   migrations; it depends on the same healthy Postgres plus Redis (the
   Taskiq broker), but not on `app-web` itself.

3. Open:
   - Frontend: <http://localhost:5173>
   - Backend API: <http://localhost:8000>
   - Interactive API docs (dev only, `ENVIRONMENT=development`):
     <http://localhost:8000/docs>

4. Check the logs if something doesn't come up:

   ```bash
   docker compose logs -f app-web
   docker compose logs -f app-worker   # background jobs: ingestion, chunking, embeddings
   docker compose logs -f frontend
   ```

## Creating the first admin

No HTTP endpoint grants the admin role — registration always creates a plain
user. Register an account through the UI (or `POST /auth/register`), then
promote it from the CLI:

```bash
docker compose exec app-web app users set-role <name> admin
```

Re-running it is a no-op. The reverse (`... set-role <name> user`) revokes
that account's sessions, as does resetting a password:

```bash
docker compose exec app-web app users reset-password <name>
```

The new password is prompted for twice and hidden — never pass it as an
argument.

## Adding a motorcycle to the catalogue

Once signed in as admin, open <http://localhost:5173/admin> to add a model by
name, watch ingestion progress live, and review/approve the result. See
`docs/modules/ingestion.md` for the full flow, the ingestion CLI commands, and the
re-chunk/re-embed commands.

## CLI reference

Every sub-app below is invoked as `docker compose exec app-web app <name> <command> ...`
(swap for `docker compose exec app-worker ...` or, outside Docker, `uv run app ...`
from `backend/` — see "Running the backend locally with uv"). `docs/modules/ingestion.md`
covers `ingest`, `chunks`, `embeddings`, `llm` and `jobs` in full detail with
worked examples; `seed`, `snapshot` and `suggestions` are spelled out below.

| Sub-app | Purpose |
|---|---|
| `catalogue` | Deterministic, no-LLM corrections to an existing entry (`set-manufacturer`). |
| `chunks` | Rebuild retrievable chunks from already-stored documents (`rebuild [slug]`). |
| `embeddings` | Rebuild the vector half of the knowledge base (`rebuild`). |
| `ingest` | Drive the ingestion building blocks directly (`run`, `probe`, `fetch-url`, `fetch-image`, `extract-specs`). |
| `jobs` | Enqueue a background job to smoke-test the Taskiq broker (`ping`). |
| `llm` | Smoke-test the OpenRouter chat and embeddings connection (`ping`, `embeddings-smoke`). |
| `openapi` | Export the OpenAPI schema without a running server (`export`). |
| `operations` | Drive a fake operation through its lifecycle, to test the live-progress path without ingestion (`demo`). |
| `rag` | Run the whole advanced-RAG pipeline and print every stage — translated queries, filters, shortlist, fused chunks (`ask "<utterance>"`). |
| `retrieval` | Query the hybrid retriever directly, no chat or agent loop (`search "<query>"`). |
| `seed` | Populate the catalogue with the curated demo model list (`demo [--auto-approve]`) — see "Seeding the demo catalogue" below. |
| `snapshot` | Save the curated catalogue into the repository and restore it verbatim (`save`, `load`) — see "Restoring the demo catalogue from the snapshot" below. |
| `suggestions` | Bulk-add proposed models to the backlog, without ingesting them (`import [FILE] [--dry-run]`) — see "Suggesting models in bulk" below. |
| `tools` | Run one advisor tool in isolation, printing exactly what the chat UI would render (`run <tool-name> --args '<json>'`). |
| `users` | Account administration, including the first-admin bootstrap (`set-role`, `reset-password`). |
| *(root)* | `app version` prints the application version. |

## Restoring the demo catalogue from the snapshot

The fastest way to get a working catalogue — and the only one that needs no API
keys, no network and no waiting:

```bash
make snapshot-load                     # empty catalogue: restore
make snapshot-load ARGS=--replace      # non-empty: delete the catalogue first, then restore
```

The curated catalogue is committed to the repository under
`backend/resources/catalogue-snapshot/` (~60 MB), and `app snapshot load`
restores it verbatim: the rows, the retained raw source payload behind every
document, every product image with its three generated variants, **and the
embeddings**. Nothing is re-ingested and nothing is re-embedded, so a fresh
clone reaches a fully working advisor — retrieval, tool calls, sources,
pictures — in about fifteen seconds and at zero API cost.

The schema must be migrated first, which the `app-web` entrypoint already does
on `make up`. `load` refuses to run against a non-empty catalogue unless
`--replace` is given; either way it never touches `users`, `sessions`, `chats`,
`chat_messages`, `chat_preferences` or `operations` — accounts still come from
"Creating the first admin", and conversations plus the ingestion audit log are
per-instance state that would be misleading to restore from someone else's run.

To update the committed snapshot after curating more models:

```bash
make snapshot-save ARGS=--force        # overwrite the existing archive, then commit it
```

`save` is read-only against the database and writes as the host user, so the
result is committable directly. It refuses to overwrite an existing archive
without `--force`, and clears the old one first when forced, so a model deleted
from the catalogue does not survive as an orphaned file in the commit. Output
is deterministic: re-saving an unchanged catalogue produces no `git` diff.

This is **demo tooling, not a backup product** — it is not point-in-time
consistent against a live instance, and it deliberately is not a `pg_dump`, so
that an archive stays reviewable in `git` and survives an additive migration (a
column added later falls back to its database default; a column removed later
is a hard error rather than a silent data loss). `app snapshot --help` and the
module docstring in `backend/app/services/snapshot.py` document the archive
layout and the type encoding.

## Seeding the demo catalogue

A fresh clone starts with an empty catalogue. To *demonstrate* the app, restore
the committed snapshot instead (previous section) — it is free and instant.
`app seed demo` is the other direction: it really ingests, which is what you
want when you are curating new models rather than reproducing an existing
catalogue.

```bash
docker compose exec app-web app seed demo               # ingest, leave in review
docker compose exec app-web app seed demo --auto-approve # ingest, then approve each
```

Run it once after first-run setup, with `OPENROUTER_API_KEY` set (spec
extraction and embeddings need it) and ideally `TAVILY_API_KEY` too (otherwise
search falls back to Wikipedia-only, per "First-run setup" above). It drives
the curated list in `backend/app/cli/data/seed_models.json` through the exact
same create → ingest → transition sequence the admin UI and `app ingest run`
use — no bypass, no shortcut, so cost and timing are the same as ingesting
that many models by hand: each model takes on the order of 1–3 minutes of real
ingestion work (web search, spec extraction, embeddings) and a comparable
amount of OpenRouter/Tavily spend, with a 10-minute per-model timeout before
it's reported as failed. The command prints one progress line per model, then
a summary table and a totals line; it is safe to re-run — any model whose slug
already exists, in any status, is skipped rather than re-ingested, and a
single model failing does not stop the rest (report-and-continue). Exit code
is 1 only if every attempted (non-skipped) model failed.

`--auto-approve` promotes each successfully ingested model straight to
`approved` through the same review-transition service an admin's approval
click uses (`in_review → approved`) — it is a bulk convenience for
bootstrapping a demo catalogue, **not** a replacement for the admin review
workflow itself. `docs/modules/catalogue.md` describes reviewing and
approving one model live, by hand, to demonstrate that flow.

## Suggesting models in bulk

`app seed demo` ingests immediately, which costs an OpenRouter/Tavily run per
model. To fill the backlog with *proposals* instead — models someone thinks the
catalogue should carry, ingested later, one at a time, by an admin who decides
when — import a model list:

```bash
docker compose exec app-web app suggestions import --dry-run  # parse and report only
docker compose exec app-web app suggestions import            # write the backlog entries
```

With no path it reads `backend/resources/bike-list.txt` (200 models, ten
marques); any file in the same format works. Each line carries a name and,
optionally, year ranges, manufacturer type codes and footnote links:

```
BMW R 1200 GS (2004–2018) [K25/K50] ([Wikipedia][1])
...
[1]: https://de.wikipedia.org/wiki/BMW_R_1200_GS_K25 "BMW R 1200 GS K25"
```

Everything but the name is stored in `motorbikes.suggestion` as an unverified
**claim**, never in the typed columns and never shown to a customer: research is
what turns a claim into catalogue data. No LLM, no network, no ingestion and no
cost — each model lands in `backlog`, and the admin backlog screen's *Start
ingestion* button is what runs the pipeline. Re-running is safe: an entry whose
slug already exists is never re-created or re-ingested; it only picks up the
suggestion document if it has none yet.

Promoting a claim into `model_name` / `year_from` / `year_to` is Phase-6 work
(`docs/roadmap/roadmap.md`) — today ingestion researches the manufacturer but leaves the
year columns NULL.

## Optional observability (Langfuse)

A bonus, fully optional compose file (`compose.langfuse.yaml`) traces
individual chat-model calls (never embeddings — LangChain's embeddings
wrapper emits no callback events) to a self-hosted
[Langfuse](https://langfuse.com/) instance. Enable it by adding the file to
`COMPOSE_FILE` in `.env` (docker compose reads that variable from `.env`),
then bring the stack up:

```bash
# in .env:
#   COMPOSE_FILE=compose.yaml:compose.langfuse.yaml
# (append :compose.local.yaml if you use local overrides)
make up
```

This starts `langfuse-web`, `langfuse-worker`, `clickhouse`, `valkey`, `minio`
and a dedicated `langfuse-postgres` alongside the default stack, **and** wires
`app-web`/`app-worker` to it: the file overrides their `LANGFUSE_*`
environment with an API key pair that `langfuse-web` self-provisions on
first boot (`LANGFUSE_INIT_*`: org, project, keys and a login user), so no
manual UI setup is needed. The compose file itself contains no secrets: every
password/key/salt is interpolated from git-ignored `.env` variables
(`LANGFUSE_POSTGRES_PASSWORD`, `LANGFUSE_INIT_*`, …) documented in
`.env.dist`, and compose fails loudly if the file is enabled with any of them
unset. The three plain `LANGFUSE_*` keys in `.env` stay empty — set those
only to trace to Langfuse Cloud instead. Open <http://localhost:3000> and
sign in with the `LANGFUSE_INIT_USER_*` credentials from your `.env` to
browse traces.

Removing the file from `COMPOSE_FILE` (then `docker compose up -d` to recreate
`app-web`/`app-worker`) returns the app to its no-tracing default —
byte-identical behaviour, and even with tracing on, a Langfuse outage never
fails a chat turn. This is a bonus item: nothing else in this repo, and no
grading criterion, depends on it running. Stop the Langfuse services before
disabling the file, or Compose will later flag their containers as orphans.

**Destructive-command warning:** never run `docker compose down -v` — it
deletes the shared `postgres-data` volume, i.e. the entire dev database, not
just Langfuse's data. There is no Langfuse-scoped `down` at all: `down`
always tears down every service in the project. To stop only the Langfuse
services and leave the rest of the stack running, use `make langfuse-down`,
which stops the six services by name:

```bash
docker compose stop langfuse-web langfuse-worker clickhouse valkey minio langfuse-postgres
```

## Running the backend locally with uv

The backend's own settings (`backend/app/core/config.py`) fall back to a
`.env` at the repo root, so `uv` commands below work whether you run them
from the repo root or from `backend/`.

```bash
cd backend
uv sync                     # install deps + dev group (ruff) into backend/.venv
uv run app version          # Typer entry point, no infrastructure needed
uv run app openapi export   # prints the OpenAPI schema, no infrastructure needed
uv run ruff check .
```

`DATABASE_URL`/`REDIS_URL` in `.env.dist` point at the Compose service names
(`postgres`, `redis`), which only resolve inside the Compose network.
`compose.yaml` does not publish Postgres's or Redis's port to the host, so
running the full API (`uvicorn`, `/ready`, anything touching the database)
outside Docker isn't supported out of the box. For anything that needs the
database, run it inside the container instead:

```bash
docker compose exec app-web app version
docker compose exec app-web alembic current
```

## Running the frontend locally with pnpm

```bash
cd frontend
pnpm install
VITE_API_URL=http://localhost:8000 pnpm dev   # backend must be reachable at this URL
```

Inside Docker Compose, `VITE_API_URL` is set on the `frontend` service in
`compose.yaml` (not in `.env` — it's a fixed dev value, not a secret). Running
`pnpm dev` without it falls back to same-origin requests, which will not
reach the backend on a different port.

Other scripts (see `frontend/package.json`): `pnpm build`, `pnpm typecheck`,
`pnpm lint`, `pnpm preview`. Frontend-specific details live in
`frontend/README.md`.

## Linting and testing

The Makefile runs everything in one-off Docker containers (`app-cli` /
`node-cli`) — no host toolchain needed, and the stack does not have to be up:

```bash
make test           # backend-test + frontend-test
make backend-test   # docker compose run --rm app-cli pytest
make frontend-test  # docker compose run --rm node-cli pnpm test
make lint           # backend-lint + frontend-lint + frontend-typecheck
```

Run `make build` (or `make rebuild`, which also recreates the running stack
and renews the frontend's `node_modules` volume) after dependency changes so
the CLI images stay fresh. `make backend-cli` / `make frontend-cli` open a
bash shell in a throwaway container for ad-hoc commands.

The same checks also run directly on the host, no Docker needed:

Backend (from `backend/`, after `uv sync`):

```bash
uv run pytest                 # test suite (backend/tests/, config in pyproject.toml)
uv run ruff check .           # lint — rules configured in backend/pyproject.toml
uv run ruff format --check .  # formatting check (drop --check to apply)
```

Frontend (from `frontend/`, after `pnpm install`):

```bash
pnpm test       # Vitest, one-shot run (pnpm test:watch for watch mode)
pnpm lint       # ESLint (frontend/eslint.config.js)
pnpm typecheck  # TypeScript type check across all tsconfig projects
```

Both test suites run entirely on the host with no infrastructure: backend
tests stub the database session via FastAPI dependency overrides (never a
real engine — see the `lru_cache`'d async-engine pitfall in
`.claude/skills/qa-checklist/SKILL.md`), and frontend tests run in jsdom against a stubbed
`fetch`, so neither needs Docker Compose, Postgres, or the backend running.
Frontend test setup lives in `frontend/vitest.config.ts` and
`frontend/src/test/`.

## Regenerating the typed API client

The frontend calls the backend through a typed `openapi-fetch` client whose
types are generated from the backend's own OpenAPI schema and committed to
git (`frontend/src/api/schema.d.ts`). Whenever a backend route or schema
changes:

```bash
make generate-api
```

This exports the schema from the running `app-web` container (so the stack
must be up) and feeds it into `openapi-typescript` inside a one-off
`node-cli` container — no host Node needed. (`cd frontend && pnpm
generate:api` still works as a host-side alternative if you have pnpm.)
Commit the regenerated `schema.d.ts`. See `.claude/skills/qa-checklist/SKILL.md` for the
convention that keeps it from drifting.

## Known limitations & future work

- **Residual prompt-injection risk.** Retrieved chunks, the customer's own
  preference values and translated-query context are all wrapped in sentinel
  fence markers before reaching the model (`backend/app/llm/fencing.py`),
  with prompt text instructing the model to treat the fenced content as data,
  never as instructions. This is a mitigation, not a proof — it has been
  live-verified against specific injection payloads, not formally guaranteed
  against every possible one.
- **No token streaming.** A chat reply is returned whole once the background
  job finishes; the UI shows a progress indicator while waiting, not
  incremental tokens.
- **English-only.** Prompts, extraction and the advisor's replies are English
  only; there is no localisation of model output (the UI chrome itself is
  i18n-ready via react-i18next).
- **No rate limiting.** The API has no per-account or per-IP request
  throttling anywhere.
- **Concurrent-turn race (known open issue).** Two `POST /api/chat-messages`
  requests for the same chat in quick succession can both pass the
  "no turn already in flight" check before either commits, occasionally
  surfacing as a 409 instead of a clean queue. Tracked, not fixed — see the
  Phase-3/4 open-questions history in `docs/roadmap/`.
- **Optional Langfuse tracing is narrow.** With all three `LANGFUSE_*` keys
  set, each LLM call lands as its own independent root trace — there is no
  grouping of a turn's calls into one trace, and tool calls never appear at
  all (they run as plain Python outside any LangChain Runnable). Embeddings
  calls are excluded entirely, regardless of configuration, because
  LangChain's embeddings wrapper emits no callback events.
- **Re-embed jobs report progress on the CLI/worker logs only.** `app
  embeddings rebuild` and `app chunks rebuild` do not surface a progress
  indicator in the admin UI; follow `docker compose logs -f app-worker`.

## Further reading

Start at **`docs/README.md`** — it indexes everything. Directly useful here:

- `docs/general/project-vision.md` — what this is, and the graded requirements
- `docs/general/architecture.md` — binding architecture decisions
- `docs/general/decisions.md` — non-obvious choices, open decisions, what we did
  not build
- `docs/general/security.md` — auth, validation, prompt-injection fencing, known
  gaps
- `docs/general/backend-stack.md`, `docs/general/frontend-stack.md` — stack
  choices and why
- `docs/modules/ingestion.md` — admin ingestion flow, internals and CLI
- `docs/modules/catalogue.md`, `docs/modules/retrieval-advisor.md`,
  `docs/modules/chat-consultation.md` — the three main subsystems
- `docs/modules/demo-data.md` — seeding, snapshots, bulk import
- `docs/roadmap/roadmap.md` — phased implementation plan (history)
- `.claude/skills/qa-checklist/SKILL.md` — QA checklist and known rough edges
- `125.md` — Stage 01 task brief · `135.md` — Stage 02 task brief
