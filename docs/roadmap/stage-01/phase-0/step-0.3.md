---
phase: 0
step: "0.3"
title: OpenAPI export CLI command
summary: Typer command `app openapi export [--out PATH]` that instantiates the FastAPI app and writes openapi.json without a running server — the backend half of the type-generation pipeline.
effort: 1
dependencies: ["0.1"]
---

# Step 0.3 — OpenAPI export CLI command

**Effort: 1** — a one-file Typer command, verifiable in isolation; the backend half of the type-generation pipeline, cut at the process boundary so frontend codegen (0.5) has a single well-bounded input.

## Architect's outline

- `backend/app/cli/openapi.py` — Typer sub-command registered on the 0.1 root app; instantiates the app factory, dumps `app.openapi()` to stdout or `--out PATH`; no server needed.
- Agent assignment: **backend-dev**.

## Verification

- `docker compose exec app-web app openapi export` prints valid OpenAPI JSON (contains the `/health` path; pipe through a JSON validator).

## Risks / notes

- Keep it import-side-effect-free: the command must not touch the database, so codegen works even when postgres is down.
