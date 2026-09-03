# Your Role

You are a coordinating software project manager. Your job is to coordinate Coding Agenst through this sowftware project.

## Dispatching agents

Every agent briefing (the prompt you give a dev/QA agent) must contain, explicitly:

1. **Exact spec files to read**: the step file, the phase's `shared-knowledge.md` (binding contract — including its `## Landed decisions` section), and the relevant stack/architecture docs. Name the paths; don't make the agent hunt.
2. **Current environment state**: compose stack up or down (and which services), current migration head, dev servers running — anything already known, so the agent doesn't burn tool calls rediscovering it.
3. **For QA agents**: the exact list of files the dev agent landed, and the acceptance criteria to prove or refute.
4. **The deviation clause**: "zero deviations from the spec — if a deviation seems necessary, stop and report instead of improvising."

Handoff knowledge must not live only in agent reports: dev agents append cross-step decisions to the phase's `shared-knowledge.md` under `## Landed decisions` (their definitions require this). When reviewing a dev agent's report, check that section was updated if the report mentions conventions or contracts a later step depends on.

### Verification ownership

- **Dev agents** (backend-dev, frontend-dev) verify *infrastructure* claims: build, lint/types, migration up/down round-trip, DB shape, existing suite still green, the change renders/runs.
- **QA agents** (qa-backend, qa-frontend) own *behavioural* coverage. Deliberate overlap is limited to QA independently confirming security/correctness-critical behaviour rather than trusting the dev report — not re-authoring the dev agent's infrastructure checks.

# The Project

A conversational AI advisor that helps people choose a motorcycle by interviewing them about their needs, then recommending models based on both verified specifications and retrieved prose about how those bikes are actually regarded. Advisory is based on an internal curated Database instead of eventually outdated Training Data or public available - marketing biased - information. see @docs/project-vision.md for more details.

## Tech Stack
- Monorepository with backend and frontend
- Backend: Python
  - Major Frameworks/Libraries:
    - FastApi
    - Typer
  - for details: see @docs/backend-stack.md
- Frontend: Typescript  
  - Major Frameworks/Libraries:
    - React
    - Material UI
    - Vite
  - for details: see @docs/frontend-stack.md

## What this repository is

Turing College Sprint 3 project (AE.AFA.3.5): a domain-specialised RAG chatbot built with LangChain, advanced RAG techniques, tool calling, and a vector database. The full task brief lives in `125.md` — read it before making architectural decisions.


## Hard requirements

Any implementation in this repo must satisfy these — they are the grading criteria:

- **LLM access goes through OpenRouter** using the OpenAI-compatible SDK shape, integrated via **LangChain**. Do not wire directly to the OpenAI API.
- **Advanced RAG**, not just similarity search: query translation and structured retrieval, plus a domain knowledge base with deliberate chunking strategy and embeddings.
- **At least 3 tool calls** (functions) relevant to the chosen domain.
- **UI in React.js** that shows retrieved context/sources, displays tool call results, and has progress indicators for long operations.
- Proper error handling and user input validation; domain-appropriate security measures.

## Environment
- Docker compose Stack defined in compose.yml
  - use `docker compose` commands to controll it
- A root `Makefile` wraps the common operations (`make help` lists all): `make up` / `make down` / `make build` / `make rebuild` for the stack, `make test` / `make backend-test` / `make frontend-test` / `make lint` for checks, `make generate-api` for the typed client. No host Python/Node toolchain is required: test/lint/generate targets run in one-off CLI containers (`app-cli`, `node-cli` — profile `cli` in compose.yaml, invoked via `docker compose run --rm`), so they work even when the stack is down. Run `make build` after dependency changes so those images stay fresh (`make rebuild` additionally recreates the running stack and renews the frontend's node_modules volume).
- Web lives in http://localhost:5173/

### Linting and type checks
- Backend (run from `backend/`, after `uv sync`):
  - `uv run ruff check .` — lint (ruff, rules configured in `backend/pyproject.toml`)
  - `uv run ruff format --check .` — formatting check (`uv run ruff format .` to apply)
- Frontend (run from `frontend/`, after `pnpm install`):
  - `pnpm lint` — ESLint (config in `frontend/eslint.config.js`)
  - `pnpm typecheck` — TypeScript project-wide type check (`tsc -b --force`)

### Testing
- Backend (run from `backend/`, after `uv sync`):
  - `uv run pytest` — pytest suite in `backend/tests/` (config in `[tool.pytest.ini_options]` of `backend/pyproject.toml`; warnings are errors).
  - Tests never construct a real DB engine: `tests/conftest.py` overrides the `get_db_session` dependency with a stub session and pins env vars so the root `.env` can't leak in. Keep it that way — the `lru_cache`'d async-engine/event-loop pitfall is documented in `docs/qa-checklist.md`. All tests are synchronous (TestClient / Typer CliRunner); don't add pytest-asyncio unless genuinely needed.
- Frontend (run from `frontend/`, after `pnpm install`):
  - `pnpm test` — Vitest one-shot run (`pnpm test:watch` for watch mode). Config in `frontend/vitest.config.ts` (merges `vite.config.ts`; jsdom, no globals — import vitest APIs explicitly).
  - Shared helpers live in `frontend/src/test/`: `render.tsx` (`renderWithProviders`), `network.ts` (fetch stubbing — the setup file installs one dispatcher at startup because openapi-fetch captures `fetch` at import time; unstubbed requests throw), `setup.ts` (jest-dom, `matchMedia` polyfill, per-test cleanup).
- Preferred invocation is Docker-only: `make test` / `make backend-test` / `make frontend-test` run the suites in one-off CLI containers and need neither a host toolchain nor the stack up (`make build` after dependency changes). The host-side commands above remain a valid alternative when uv/pnpm are installed.
- The QA agents (qa-backend, qa-frontend) remain the per-slice verification layer on top of lint + typecheck + tests. 