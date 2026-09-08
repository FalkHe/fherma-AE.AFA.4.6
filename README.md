# AI Dungeon Master

A single-player Dungeons & Dragons (5e SRD) game run entirely by an AI agent.
The agent narrates, interprets free-form player actions, rolls dice, looks up
rules and keeps game state consistent across play sessions — so you can try
pen & paper without a group and without learning the rules first.

This is the AE.AFA.4.6 Turing College Sprint 4 project. `135.md` is the
binding brief. `docs/general/project-vision.md` describes the design.

## Current state

Scaffolding. The repository carries the Docker environment, the modular
backend and frontend skeletons, and username/password authentication. The
game agent itself is not built yet.

## Quick start

Everything runs in Docker; no host Python or Node toolchain is required. Make
sure ports `5173` and `8000` are free.

```bash
cp .env.dist .env       # every default works out of the box
make up                 # API, frontend, Postgres; migrates the DB on boot
```

Open <http://localhost:5173>, register a username and password, and sign in.

- Frontend: <http://localhost:5173>
- Backend API: <http://localhost:8000>
- Interactive API docs (dev only): <http://localhost:8000/docs>

`make down` stops everything. `make help` lists every target.

`OPENROUTER_API_KEY` is not needed yet — nothing calls a model until the game
agent lands — but set it now if you have one; every LLM call in this project
goes through OpenRouter.

## Stack

- **Backend**: Python, FastAPI, Typer, SQLAlchemy 2 (async), Alembic,
  PostgreSQL (pgvector), LangChain/LangGraph over OpenRouter. No background
  job runner and no Redis — every operation is request-scoped or a CLI
  one-off. See `docs/general/backend-stack.md`.
- **Frontend**: TypeScript, React, Material UI, Vite, TanStack Query, React
  Router, react-i18next. See `docs/general/frontend-stack.md`.
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
make lint            # ruff, ESLint, tsc (backend-lint / frontend-lint / frontend-typecheck)
make generate-api    # regenerate the frontend's typed API client (stack must be up)
make build           # rebuild images after a dependency change
make rebuild         # build, then recreate the stack and renew node_modules
```

Test and lint targets run in one-off CLI containers (`app-cli`, `node-cli`,
compose profile `cli`), so they work with the stack down. Run `make build`
after changing dependencies so those images stay fresh.

Optional Langfuse tracing lives in `compose.langfuse.yaml`. Enable it per
checkout by adding it to `COMPOSE_FILE` in `.env`, filling in the
`LANGFUSE_*` secrets that `.env.dist` documents, and running `make up`;
without it the app behaves identically with tracing off.

## Documentation

`docs/README.md` is the index. Start there for architecture and subsystem
detail.
