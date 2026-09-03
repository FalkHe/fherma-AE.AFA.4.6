---
phase: 2
step: "2.5"
title: Taskiq broker & worker service
summary: Taskiq + taskiq-redis wiring, the app-worker Compose service (same image, worker entrypoint, never migrates), a demo.ping task and an `app jobs ping` CLI command proving the loop.
effort: 2
dependencies: ["0.1"]
agent: backend-dev
track: backend
---

# Step 2.5 — Taskiq broker & worker service

**Effort: 2** — mechanical wiring plus the retry-middleware decision.
Independent of the 2.1→2.3 mainline — parallelizable in a second backend
session (merge-friction files listed in shared-knowledge).

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *Taskiq wiring* (broker
module, task naming, worker command, retry policy) and the Phase-1 *CLI
async pattern*. `docs/architecture.md` → *Background Jobs*. Zero deviations;
stop and report if one seems necessary.

## Files

- Create `backend/app/jobs/__init__.py`, `broker.py`, `demo.py`
- Create `backend/app/cli/jobs.py`
- Create `backend/tests/cli/test_jobs.py`
- Modify `compose.yaml` (`app-worker` service), `backend/pyproject.toml` +
  `uv.lock` (`taskiq`, `taskiq-redis`), `backend/app/cli/main.py`

## Implementation outline

- `broker.py`: `ListQueueBroker(url=settings.redis_url)`, no result backend.
- `demo.py`: `demo.ping` task (logs and returns).
- `app jobs ping`: enqueues via the Phase-1 CLI async pattern
  (`asyncio.run(_impl())`).
- `app-worker` per the pinned Compose shape: same image/env/bind-mount,
  `entrypoint: []`, `taskiq worker app.jobs.broker:broker app.jobs.demo`,
  depends on postgres (healthy) + redis (started), **never runs migrations**.
- Retry middleware is **pinned** (shared-knowledge → *Taskiq wiring*):
  `SmartRetryMiddleware` with `types_of_exceptions=[TransientJobError]` and
  the pinned constructor args, attached via `.with_middlewares(...)`;
  define `TransientJobError` in `jobs/__init__.py`. Retryable tasks carry
  `retry_on_error=True` on their decorator.
- Run `make build` after the dependency change.

## Verification

- `docker compose up -d app-worker` boots clean;
  `docker compose run --rm app-cli app jobs ping` → worker log shows the task
  ran. `make backend-test` green (broker import-safe without Redis; CLI test
  with a stubbed kicker).

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
