---
phase: 5
step: "5.15"
title: README — CLI reference, seed, Langfuse profile, limitations
summary: Extend the landed README with a CLI reference (13 sub-apps incl. seed), seed instructions, the optional Langfuse profile section, and the honest known-limitations list. The template is .env.dist everywhere.
effort: 3
dependencies: ["5.9", "5.10", "5.11"]
---

# Step 5.15 — README: CLI reference, seed, Langfuse profile, limitations

**Effort: 3** — writing against landed behaviour (S2: starts only after
backend 5.11 is merged, so seed + Langfuse are final).

Binding contract: `docs/roadmap/phase-5/shared-knowledge.md` (D8; also read
the Landed decisions of 5.9/5.10/5.11 for exact commands/ports/output).
Agent: **docs-writer**. Zero deviations — a deviation is a stop-and-report.

**Environment:** stack up to replay every documented command verbatim before
writing it down.

## Outline

- `README.md` — **extend, don't rewrite** (the quickstart/prereqs/first-admin
  /lint-test sections landed in earlier phases and stand):
  - **CLI reference**: one table over the 13 sub-apps (`catalogue chunks
    embeddings ingest jobs llm openapi operations rag retrieval seed tools
    users`) + `version`, one line each, with the seed command spelled out
    (`app seed demo [--auto-approve]`, skip-if-exists, report-and-continue).
  - **Seeding the demo catalogue**: when to run it, cost/time expectations,
    what `--auto-approve` does and doesn't (bulk approval ≠ the admin-review
    story — one live review stays in the walkthrough).
  - **Optional observability (Langfuse)**: `--profile langfuse`, the three
    `LANGFUSE_*` keys, the UI port, explicitly optional/bonus.
  - **Known limitations & future work** (the D8 list, honest wording):
    residual prompt-injection risk (fencing is mitigation), no token
    streaming, English-only, no rate limiting, the concurrent-turn 409 race
    (Phase-4 OQ4, known open issue), demo prices are owner-approved guesses
    (Phase-4 OQ2), Langfuse tracing excludes embeddings, re-embed jobs
    report progress on the CLI only.
  - Every reference to the env template says **`.env.dist`**.
- Link check: `docs/architecture.md`, `docs/demo-walkthrough.md` (5.16 will
  extend it — link stays valid), the future `docs/grading-map.md` link is
  added by 5.16, not here.

## Verification

- A reader can execute every documented command verbatim from a fresh shell
  (spot-replay them); links resolve; no stale ".env.example" or
  "demo-script" wording anywhere in the repo docs (`git grep`).

## Risks / notes

- Do not present seeded/guessed data as verified (OQ2 wording rule).
- Append (`### Step 5.15`) to `shared-knowledge.md` if any documented
  behaviour was found to deviate from a landed decision (that's a report,
  not a silent doc-fix).
