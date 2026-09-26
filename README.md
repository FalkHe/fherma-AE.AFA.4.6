# AI Dungeon Master

A single-player Dungeons & Dragons (5e SRD) game run entirely by an AI agent.
The agent narrates, interprets free-form player actions, rolls dice, looks up
rules and keeps game state consistent across play sessions — so you can try
pen & paper without a group and without learning the rules first.

This is the AE.AFA.4.6 Turing College Sprint 4 project. `135.md` is the
binding brief; `docs/general/requirement-map.md` maps it onto the system.
`docs/general/app-vision.md` describes what the app is for.

The project proves knowledge of AI agents — prompting, RAG, tools, memory,
human-in-the-loop — not game design, so everything else stays minimal. It is
single player, and three layers stay separate: **content** (campaigns,
adventures, scenes and stat blocks as static JSON), **reasoning** (the LLM
agent) and **mechanics** (deterministic tools for dice, hit points and state
validation). The agent never fakes a roll and never edits state directly.
Only the SRD rules text is RAG. See `docs/general/architecture.md`.

## Current state - Stage 01 ( AE Sprint 3 )

The app includes username/password authentication, campaign selection,
AI-assisted character creation, and a playable Dungeon Master agent with
deterministic mechanics, persistent game state, and SRD rule retrieval.

**Implemented Features:**
- basic persistent game schema and mechanics
- first Campaign + 1 Adventure Story
- SRD Rule ingestion (embedding)
- simple character creation agent
- **The Dungeon Master Agent ( core of this Project )**
- Langfuse / Langsmith Tracing

**Planned Features - Stage 02 ( AE Capstone )**
- advanced DM Agent
  - Optimized Context
  - Optimized Prompts ( automated Walkthrough tests  with analysis)
- Party sidebar ( display current, stats, scene, etc. )
- Narration token Streaming
- automated Image generation for Adventures, Scenes and Characters
- polished frontend
- evtl. multiplayer mode

## Quick start

Everything runs in Docker; install Docker with Compose and Make. No host
Python or Node toolchain is required. Make sure ports `5173` and `8000` are
free.

```bash
cp .env.dist .env
```

Set `OPENROUTER_API_KEY` in `.env` before continuing. All model calls go
through OpenRouter, including chat, embeddings and portraits. The app can
start without a key, but AI character creation and gameplay need one.
The model defaults are in `.env.dist`.

```bash
make build              # builds app and CLI images
make up                 # API, frontend, Postgres; migrates the DB on boot
```

Once the API has finished starting (check `docker compose logs app-web`),
load the SRD rules into a fresh database:

```bash
docker compose run --rm app-cli app srd ingest
docker compose run --rm app-cli app srd status
```

CLI containers join the Compose network but do not start Postgres or run
migrations themselves; the `make up` above provides both.

Ingestion uses the bundled `backend/content/srd/v1/SRD_CC_v5.1.md` and calls
OpenRouter for embeddings, incurring model usage costs. It only needs to run
once per database unless you want to replace the rules corpus; `make down` preserves the database
volume. Campaign content is already included in `backend/content/campaigns/`.

To explicitly download a replacement SRD source before ingesting, add
`--refresh-source`. Use `--dry-run` to preview chunks without embeddings or
database writes; it uses the local file unless combined with `--refresh-source`.

Open <http://localhost:5173>, register a username and password, and sign in.
Start a campaign, create your character, and begin an adventure.

- Frontend: <http://localhost:5173>
- Backend API: <http://localhost:8000>
- Interactive API docs (dev only): <http://localhost:8000/docs>

`make down` stops everything. `make help` lists every target.

### Optional tracing: Langfuse and LangSmith

Both services are external; Compose does not host either of them. You can
enable either or both in `.env`, or leave tracing disabled for local play.

- **Langfuse** captures chat, embedding and image calls through
  `backend/app/core/tracing/`. Set `LANGFUSE_PUBLIC_KEY`,
  `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL` for your external project.
  Replace the example base URL in `.env.dist` with your instance's URL.
  Leaving any of the three blank disables Langfuse. Tracing failures are
  logged without failing model calls.
- **LangSmith** is picked up by LangChain itself from the environment; the
  backend contains no LangSmith-specific code. Set
  `LANGSMITH_TRACING=true`, replace the `LANGSMITH_API_KEY` placeholder with
  your key, and set `LANGSMITH_PROJECT` to your project name. Set
  `LANGSMITH_ENDPOINT` to your external service's API endpoint (the template
  uses `https://api.smith.langchain.com`). Direct OpenRouter SDK calls for
  embeddings and images are not automatically captured by LangSmith.
  Keep `LANGSMITH_TRACING=false` to disable it.

Both endpoints must be reachable from inside the backend containers.
After changing `.env` for a running stack, recreate the API container:

```bash
docker compose up -d --force-recreate app-web
```

New `app-cli` containers pick up the updated values automatically.

## Stack

- **Backend**: Python 3.12, FastAPI, Typer, SQLAlchemy 2 (async), Alembic,
  PostgreSQL 16 (pgvector), LangChain/LangGraph over OpenRouter, Langfuse SDK. No background
  job runner and no Redis — every operation is request-scoped or a CLI
  one-off. See `docs/general/backend-stack.md`.
- **Frontend**: TypeScript, React 19, Material UI 9, Vite, TanStack Query,
  React Router, react-i18next; Vitest and Testing Library for tests. See `docs/general/frontend-stack.md`.
- **Architecture and conventions**: `docs/general/architecture.md`.

Both trees are organised by domain **module** rather than by technical layer:

```
backend/app/modules/<module>/     models.py schemas.py routes.py service.py
backend/tests/<module>/           mirrors the above one-to-one
frontend/src/modules/<module>/    components/ hooks/ routes/
```

`core/` on either side holds only what two or more modules need.

## Development

```bash
make test            # both suites (backend-test / frontend-test individually)
make backend-test-db # opt-in tests against a scratch Postgres database
make lint            # ruff, ESLint, tsc (backend-lint / frontend-lint / frontend-typecheck)
make generate-api    # regenerate the frontend's typed API client (stack must be up)
make build           # rebuild images after a dependency change
make rebuild         # build, then recreate the stack and renew node_modules
```

Test and lint targets run in one-off CLI containers (`app-cli`, `node-cli`,
compose profile `cli`), so they work with the stack down. Run `make build`
after changing dependencies so those images stay fresh.

## Documentation

`docs/README.md` is the index. Start there for architecture and subsystem
detail.

## License

This work includes material taken from the System Reference Document 5.1
("SRD 5.1") by Wizards of the Coast LLC and available at
https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1
is licensed under the Creative Commons Attribution 4.0 International
License available at https://creativecommons.org/licenses/by/4.0/legalcode
