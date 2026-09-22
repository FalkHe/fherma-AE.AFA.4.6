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

### Public hostname / SSL reverse proxy

The stack can remain in `ENVIRONMENT=development` behind an HTTPS reverse
proxy. Configure the browser-facing addresses in `.env`:

```dotenv
VITE_API_URL=https://dnd.example.com
VITE_ALLOWED_HOST=dnd.example.com
FRONTEND_ORIGIN=https://dnd.example.com
```

For one public hostname, route `/api/*` to `127.0.0.1:8000` and all other
requests to `127.0.0.1:5173`. If the API uses a separate hostname, put that
origin in `VITE_API_URL`; `FRONTEND_ORIGIN` must still be the exact frontend
origin. Recreate the affected services after changing these values:

```bash
docker compose up -d --force-recreate frontend app-web
```

The proxy must disable response buffering for `/api/*` so campaign SSE updates
are delivered immediately, and it must support WebSocket upgrades for the Vite
development server.

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

Langfuse tracing is wired into the LLM seam (`backend/app/core/tracing/`)
and points at an external Langfuse instance — nothing is hosted here. Fill
in `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL` in
`.env` to switch it on; leave any of them empty and the app behaves
identically with tracing off. A Langfuse outage never fails a model call.

## Documentation

`docs/README.md` is the index. Start there for architecture and subsystem
detail.

## License

This work includes material taken from the System Reference Document 5.1
("SRD 5.1") by Wizards of the Coast LLC and available at
https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1
is licensed under the Creative Commons Attribution 4.0 International
License available at https://creativecommons.org/licenses/by/4.0/legalcode
