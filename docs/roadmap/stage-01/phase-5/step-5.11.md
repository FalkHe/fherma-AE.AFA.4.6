---
phase: 5
step: "5.11"
title: Seed model list & `app seed demo`
summary: Curated ~12-model seed list + a Typer seed command running the real ingestion pipeline per model — skip-if-exists in any status, report-and-continue, --auto-approve via the standard transition service. Exit 1 only if every model failed.
effort: 4
dependencies: ["5.6"]
---

# Step 5.11 — Seed model list & `app seed demo`

**Effort: 4** — the command is modest, but the live seed run (real web
search + LLM extraction per model) plus failure-tolerance testing consumes
the rest of a slice.

Binding contract: `docs/roadmap/stage-01/phase-5/shared-knowledge.md` (D7). Prior
pins: Phase-2b fresh-run semantics (**re-ingestion deletes documents and
embeddings — the seed must never re-ingest an existing model**, any status);
Phase-2 transition matrix (approval side effects live in
`product_service.transition` — no status bypass); the CLI `_fail` convention
(Phase-1 SK); DB-touching CLI commands get no test file for the live path
(the 2.19 precedent) — test the orchestration with stubs. Agent:
**backend-dev**. Zero deviations — a deviation is a stop-and-report.

**Environment:** stack up with worker running; `OPENROUTER_API_KEY` +
`TAVILY_API_KEY` live. Seed ingestion costs money and time (~1–3 min/model)
— run it once, sequentially.

## Outline

- `backend/app/cli/data/seed_models.json`: ~12 models spanning A2-eligible
  beginners, tourers, nakeds (convincing interview coverage). Include the
  names only (`[{"name": "…"}, …]`) — everything else comes from the
  pipeline. Deliberately exclude the 3 dev-DB models is *not* required —
  skip-if-exists covers them — but avoid names whose slug collides with the
  demo's live-review bike ("Suzuki GSR 600" stays free for the walkthrough's
  admin-review chapter; it already exists in the dev DB as Suzuki GSR600 —
  fine, different slug is NOT guaranteed, so check and pick accordingly).
- New `backend/app/cli/seed.py`, registered in `cli/main.py` (13th sub-app,
  alphabetical): `app seed demo [--auto-approve]`. Per model, sequentially:
  1. `slugify(name)` → if a motorbike with that slug exists in **any**
     status: print `skipped (exists: <status>)`, continue.
  2. Create via the standard backlog path (`product_service.create_backlog`)
     and start ingestion exactly as the admin flow does (transition →
     enqueue) — **same pipeline, no bypass**.
  3. Poll the operation (reuse `operation_service` reads; modest timeout,
     e.g. 10 min/model) → on `failed`, print the error, continue.
  4. With `--auto-approve` and a succeeded run: `transition(in_review →
     approved)` via the service (promotes draft → verified, approves images
     — the pinned side effects).
  5. Print a final summary table (model → seeded/approved/skipped/failed);
     exit 1 **only if every non-skipped model failed**.
- Tests (CliRunner + stubs, no DB/network): skip-if-exists, report-and-
  continue on a failing model, auto-approve calls the transition service,
  exit-code rules.

## Verification

- Suite + lint green.
- Live: `docker compose exec app-web app seed demo --auto-approve` on the
  dev DB → the 3 existing models are skipped, the rest ingest;
  `GET /api/catalogue-models` lists ≥ 10 approved models; spot-check one
  seeded detail page (specs, article, sources, image).

## Risks / notes

- Individual models can flake (search quality, fetch timeouts) — that is
  what report-and-continue is for; do not add retries beyond the pipeline's
  own (`SmartRetryMiddleware` already retries transient job errors).
- Keep the list small enough to ingest in one sitting; 150 models is a
  production goal, not a demo requirement.
- Auto-approved models weaken the "admin-verified" story if oversold — the
  walkthrough (5.16) still demoes one live admin review; docs must say the
  seed's approval is bulk.
- Append (`### Step 5.11`) to `shared-knowledge.md`: the final model list,
  polling/timeout choices, and the summary-output format — 5.16/5.18 script
  against them.
