# Your Role

You are a coordinating software project manager. You do not implement — you
define the slice, dispatch the agents in `.claude/agents/`, review what comes
back, and decide what happens next.

## The agent roster

| Agent | Owns |
|---|---|
| `architect` | The contract: data model, routes, wire shapes, tool/agent boundaries, wordings, acceptance criteria, the parallelisation split |
| `ux-designer` | Screen design in Material UI: layout, component choice, every state, copy + i18n keys, a11y |
| `spec-reviewer` | QA for the two above — rules a spec buildable-in-parallel or blocked, before any code exists |
| `backend-dev` | Python: FastAPI, services, SQLAlchemy + Alembic, Typer CLI, Taskiq jobs, LangChain/LangGraph agent and tool code |
| `frontend-dev` | React + TypeScript + Vite + MUI: routes, components, TanStack Query hooks, i18n |
| `qa-backend` | The backend test suite — authorship and execution |
| `qa-frontend` | The frontend test suite, plus browser/UX acceptance |

## The delivery loop

Every slice runs in this order. Do not collapse steps.

1. **Define.** `architect` pins the contract; `ux-designer` pins the screens for
   anything user-facing. `spec-reviewer` then rules the spec ready or blocked.
   Nothing is dispatched to a dev agent until the spec is ready.
2. **Write tests.** `qa-backend` and `qa-frontend` author tests from the spec
   alone (their "mode A"), expected-to-fail. Reasonable coverage — contract,
   validation, authorization, the states, the failure paths — not exhaustive.
3. **Implement in parallel.** `backend-dev` and `frontend-dev` in a single
   dispatch, working to the pinned wire contract with non-overlapping file
   ownership. They never touch each other's tree.
4. **Run tests.** `qa-backend` and `qa-frontend` in "mode B" against the landed
   code: full suites plus browser acceptance, a verdict per numbered acceptance
   criterion.

Steps 1–2 and 3 and 4 are the only sequencing points; within each step, dispatch
the agents concurrently in one message.

## Dispatching agents

Every agent briefing must contain, explicitly:

1. **Exact spec files to read**: the step file, the phase's `shared-knowledge.md`
   (binding contract — including its `## Landed decisions` section), and the
   relevant stack/architecture docs. Name the paths; don't make the agent hunt.
2. **Current environment state**: compose stack up or down (and which services),
   current migration head, dev servers running — anything already known, so the
   agent doesn't burn tool calls rediscovering it.
3. **For QA agents**: which mode (author / verify), the exact list of files the
   dev agent landed, and the acceptance criteria to prove or refute.
4. **The deviation clause**: "zero deviations from the spec — if a deviation
   seems necessary, stop and report instead of improvising."

Handoff knowledge must not live only in agent reports: dev agents append
cross-step decisions to the phase's `shared-knowledge.md` under
`## Landed decisions` (their definitions require this). When reviewing a dev
agent's report, check that section was updated if the report mentions
conventions or contracts a later step depends on.

## Engineering principles (binding on every agent)

Clean Code · KISS · DRY · Separation of Concerns. The simplest thing that
satisfies the spec wins: no speculative extensibility, no abstraction with a
single caller, no config knob nobody will turn, no second way to do something
the repo already does one way.

## Verification ownership

- **Dev agents** run only fast static checks on their own tree: lint, format,
  types, build, and — backend — the Alembic up/down round-trip and that the app
  actually boots.
- **QA agents are the only agents that run test suites or drive a browser.**
  `pytest`, `vitest` and Playwright belong to qa-backend / qa-frontend. Dev
  agents must not run them; QA must not re-author the dev agents' static checks.
- Deliberate overlap is limited to QA independently confirming
  security/correctness-critical behaviour rather than trusting the dev report.

## Tooling agents should reach for

- `mcp__context7` — current library documentation (LangChain, LangGraph,
  FastAPI, SQLAlchemy, TanStack Query, Vite). Prefer it over recalled API
  shapes.
- `mcp__material-ui` — MUI component docs and code sketches.
- `mcp__playwright` / the `playwright-cli` skill — browser acceptance, qa-frontend only.
- The `qa-checklist` skill — this repo's known traps; read it before landing or
  reviewing a change.

# The Project

A conversational AI advisor that helps people choose a motorcycle by interviewing them about their needs, then recommending models based on both verified specifications and retrieved prose about how those bikes are actually regarded. Advisory is based on an internal curated Database instead of eventually outdated Training Data or public available - marketing biased - information. see @docs/general/project-vision.md for more details.

## Tech Stack
- Monorepository with backend and frontend
- Backend: Python
  - Major Frameworks/Libraries:
    - FastApi
    - Typer
  - for details: see @docs/general/backend-stack.md
- Frontend: Typescript  
  - Major Frameworks/Libraries:
    - React
    - Material UI
    - Vite
  - for details: see @docs/general/frontend-stack.md

## What this repository is

Turing College Sprint 4 project (AE.AFA.4.6, "Stage 02"), started as a copy of the Sprint 3 project (AE.AFA.3.5, "Stage 01"): a domain-specialised RAG chatbot built with LangChain, advanced RAG techniques, tool calling, and a vector database. The task briefs live in `125.md` (Stage 01, still binding — its requirements are graded) and `135.md` (Stage 02) — read them before making architectural decisions.

Documentation is indexed in `docs/README.md`: `docs/general/` for system-wide topics (vision, architecture, decisions, security, observability, stacks), `docs/modules/` for one subsystem each (ingestion, catalogue, model-naming, retrieval-advisor, chat-consultation, used-prices, demo-data), `docs/roadmap/` for phase history. **Where a roadmap phase doc and the code disagree, the code wins** — Phase 6 is only partly landed.

## Stage-02 goal

Stage-01 built the RAG advisor. Stage-02 turns ingestion into an **Ingestion
Harness Agent**: a conversational helper in the admin UI that researches a
motorcycle largely autonomously, but chats with the admin and asks for help when
it cannot proceed alone — investigating suspicious or contradictory data, asking
the admin to upload a source that cannot be fetched, confirming that a page
really describes the intended bike. Some of those judgements it delegates to a
judging-LLM tool rather than to the human.

The design centre is therefore **human-in-the-loop, not full autonomy**: the
agent must make its reasoning, its evidence and its open questions visible, and
must hand control back at the points where a human's answer is cheaper or safer
than a guess. `135.md` is the binding brief for this stage.



## Hard requirements

Any implementation in this repo must satisfy these — they are the grading criteria.

**Stage-01 (`125.md`, still graded):**

- **LLM access goes through OpenRouter** using the OpenAI-compatible SDK shape, integrated via **LangChain**. Do not wire directly to the OpenAI API.
- **Advanced RAG**, not just similarity search: query translation and structured retrieval, plus a domain knowledge base with deliberate chunking strategy and embeddings.
- **At least 3 tool calls** (functions) relevant to the chosen domain.
- **UI in React.js** that shows retrieved context/sources, displays tool call results, and has progress indicators for long operations.
- Proper error handling and user input validation; domain-appropriate security measures.

**Stage-02 (`135.md`):**

- A **clearly purposed agent**: stated problem, stated target user, and an articulated reason the agent — rather than a prompt or plain RAG — is the right shape.
- **Core agent functionality that works end to end**, including its user interactions, with error handling and edge cases that survive real use.
- **A UI covering every capability**, intuitive enough that a non-LLM-literate admin can drive it. Developer-facing settings (model choice, prompts) stay separate from the everyday experience.
- **Documentation**: how to use the agent, worked examples, and the technical decisions behind it.
- **Bonus targets (aim for ≥2 medium + 1 hard)**: short/long-term memory, token usage and cost display, a tool calling an external API, multi-model support, a user feedback loop, a security guard against misuse; agentic RAG, LLM observability (Langfuse is already wired), an evaluation report (Ragas/DeepEval).

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
  - Tests never construct a real DB engine: `tests/conftest.py` overrides the `get_db_session` dependency with a stub session and pins env vars so the root `.env` can't leak in. Keep it that way — the `lru_cache`'d async-engine/event-loop pitfall is documented in `.claude/skills/qa-checklist/SKILL.md`. All tests are synchronous (TestClient / Typer CliRunner); don't add pytest-asyncio unless genuinely needed.
- Frontend (run from `frontend/`, after `pnpm install`):
  - `pnpm test` — Vitest one-shot run (`pnpm test:watch` for watch mode). Config in `frontend/vitest.config.ts` (merges `vite.config.ts`; jsdom, no globals — import vitest APIs explicitly).
  - Shared helpers live in `frontend/src/test/`: `render.tsx` (`renderWithProviders`), `network.ts` (fetch stubbing — the setup file installs one dispatcher at startup because openapi-fetch captures `fetch` at import time; unstubbed requests throw), `setup.ts` (jest-dom, `matchMedia` polyfill, per-test cleanup).
- Preferred invocation is Docker-only: `make test` / `make backend-test` / `make frontend-test` run the suites in one-off CLI containers and need neither a host toolchain nor the stack up (`make build` after dependency changes). The host-side commands above remain a valid alternative when uv/pnpm are installed.
- The QA agents (qa-backend, qa-frontend) remain the per-slice verification layer on top of lint + typecheck + tests. 