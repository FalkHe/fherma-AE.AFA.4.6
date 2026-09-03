---
phase: 5
step: "5.1"
title: Error handling & validation sweep (split — replaced by steps 5.4–5.8, 5.12–5.14, 5.17)
summary: SPLIT. The former effort-8 hardening sweep was re-sliced (2026-08-28) into parallel backend/frontend steps with max effort 4 each. See shared-knowledge.md for the binding contract and the mapping below.
effort: 0
dependencies: []
---

# Step 5.1 — Error handling & validation sweep (split)

**This step no longer exists as dispatchable work.** During the Phase-5
slicing (2026-08-28) its effort-8 scope was split into parallel-track steps
of max effort 4, with the open design points resolved and pinned in
[`shared-knowledge.md`](shared-knowledge.md) (decisions D1–D4, D9).

| Former 5.1 scope | Now lives in |
|---|---|
| "Unified error envelope … in `backend/app/api/errors.py`" | **Superseded by D1**: only a 500 catch-all was missing; it is registered in `main.py` per the Phase-2 one-handler pin — step 5.4. No `api/errors.py`. |
| Schema validation sweep | 5.5 (the exhaustive close-list is D2, incl. the owner-approved login password cap — resolved OQ-A) |
| LLM failure states (`LlmUnavailableError`, `LlmOutputError`, retry budget) | **Mostly already landed** (apology path, `TransientJobError`, typed failure reasons — Phases 2/3). The real gap was client timeouts: 5.6 (D3). No new exception taxonomy. |
| Ingestion failure states (per-stage recording) | **Superseded by the Phase-2 warning-policy pin + zero-migrations rule** (D2 resolution) — no step. Stage milestones, retry button and abandon-to-backlog already exist. |
| Prompt-injection defences | 5.7 (fencing module extraction) + 5.8 (advisor/query-translation/preference fencing) — D4 |
| Frontend non-executable content check / shared `Markdown.tsx` | 5.12 (`UntrustedMarkdown`, ui-spec §4) — raw HTML was already off at all three sites; the step consolidates and adds the missing chat inertness test |
| Frontend error surfacing "via openapi-fetch middleware" | **Superseded by D9 / ui-spec §9**: the landed per-screen pattern stays; gap closures in 5.13 |
| QA pass (curl matrix, dead LLM, poisoned document) | 5.17 (M1 acceptance) |
