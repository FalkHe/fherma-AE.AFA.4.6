---
phase: 5
step: "5.18"
title: Final acceptance & fresh-clone verification
summary: On a clean checkout with only .env filled from .env.dist, follow the README verbatim — compose up, admin bootstrap, seed, full demo walkthrough, optional Langfuse spot-check. Every deviation is a doc bug fixed before tagging phase-5-done.
effort: 4
dependencies: ["5.10", "5.16", "5.17"]
---

# Step 5.18 — Final acceptance & fresh-clone verification (QA)

**Effort: 4** — a full fresh-environment run including a live seed (real
web + LLM calls); this is the submission gate.

Binding contract: `docs/roadmap/phase-5/shared-knowledge.md` (M3 demo
criterion) plus `README.md`, `docs/demo-walkthrough.md` and
`docs/grading-map.md` exactly as landed. Agent: **qa**. Zero deviations —
**a deviation from the docs is a doc bug**: file it, have it fixed, re-run
the affected section before tagging.

**Environment:** a **fresh clone** in a scratch directory, fresh Docker
volumes (no reuse of the dev DB), `.env` copied from `.env.dist` with only
the required keys filled (`OPENROUTER_API_KEY`, `TAVILY_API_KEY`, DB/redis
defaults as shipped).

## Outline

1. Fresh clone → `cp .env.dist .env` → fill keys → `make up` — the README
   quickstart, verbatim.
2. CLI admin bootstrap per README; register a customer account in the SPA.
3. `docker compose exec app-web app seed demo --auto-approve` → ends with
   the summary table; `GET /api/catalogue-models` shows the seeded approved
   models (on a fresh DB nothing is skipped).
4. Replay `docs/demo-walkthrough.md` end to end, including the submission
   chapter (live admin review, consultation with tools/sources/cards,
   catalogue click-through, resume after logout).
5. Cross-check `docs/grading-map.md`: every row's file/endpoint/screen
   exists at the recorded location.
6. Optional (bonus, timeboxed): `docker compose --profile langfuse up` →
   one traced consultation; plain `up` unaffected.
7. File the evidence run; fix-and-re-run doc bugs; coordinator tags
   **`phase-5-done`**.

## Verification

- The M3 demo criterion in shared-knowledge answered item by item; zero
  unresolved deviations between docs and observed behaviour.

## Risks / notes

- Seed ingestion is the flakiest link (live web + LLM): per-model failures
  are tolerated by design (report-and-continue) — the criterion is ≥ 10
  approved models, not a perfect run; a systematic failure (0 models) is a
  blocker.
- Keep the scratch clone until the tag is pushed — it is the reproduction
  environment for any filed doc bug.
