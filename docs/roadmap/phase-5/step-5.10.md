---
phase: 5
step: "5.10"
title: Langfuse Compose profile
summary: Optional --profile langfuse stack (langfuse-web/worker, clickhouse, valkey, minio, dedicated langfuse-postgres); plain docker compose up starts exactly today's services. Bonus item — submission never depends on it.
effort: 3
dependencies: ["5.9"]
---

# Step 5.10 — Langfuse Compose profile

**Effort: 3** — six service definitions with wiring/env, plus the
default-stack-unchanged proof; no application code.

Binding contract: `docs/roadmap/phase-5/shared-knowledge.md` (D6). Agent:
**backend-dev** (compose-only — touches `compose.yaml` and `.env.dist`
comments, no `backend/app/` code). Zero deviations — a deviation is a
stop-and-report.

**Environment:** Docker with enough headroom for 6 extra containers; the
default stack keeps running throughout.

## Outline

- `compose.yaml`: services `langfuse-web`, `langfuse-worker`, `clickhouse`,
  `valkey`, `minio`, **`langfuse-postgres`** (dedicated — D6: the shared
  pgvector postgres keeps a single database; its existing volume would never
  re-run an init script anyway), all under `profiles: ["langfuse"]`, with
  named volumes for clickhouse/minio/langfuse-postgres and container-local
  secrets (generated defaults are fine — this is a dev/bonus stack, note
  them as such in comments). Follow the current Langfuse v3 self-hosting
  compose reference for required env (verify versions against the SDK
  landed in 5.9).
- Port choice must not collide with 5173/8000/5432/6379 — pin the Langfuse
  UI port in a comment (proposal: 3000).
- `.env.dist`: comment-only pointers (`LANGFUSE_HOST=http://localhost:3000`
  example for the self-hosted profile).
- Optional `make langfuse-up`/`langfuse-down` targets only if trivial.

## Verification

- `docker compose config --services` (no profile) lists exactly today's
  seven services — byte-identical default stack.
- `docker compose --profile langfuse up -d` → Langfuse UI reachable, project
  + API keys creatable; with those keys in `.env` (and `app-web`/`app-worker`
  restarted) one consultation shows a **full trace** — agent steps + tool
  calls — in the Langfuse UI. This is the M2 demo criterion.
- `docker compose --profile langfuse down` leaves the default stack healthy.

## Risks / notes

- This is a **bonus item** the owner has pre-authorized dropping (D5,
  resolved OQ-B/OQ-C): if it stalls on Langfuse infra quirks, timebox,
  report to the coordinator, and it gets dropped — no owner round-trip, no
  fallback engineering.
- Never let later steps or docs make submission depend on this profile
  running.
- Append (`### Step 5.10`) to `shared-knowledge.md`: image tags/versions
  chosen and the UI port — 5.15 documents them.
