---
phase: 5
step: "5.16"
title: Grading map + demo-walkthrough submission chapter
summary: New docs/grading-map.md mapping every core requirement and claimed bonus to concrete files/endpoints/screens; docs/demo-walkthrough.md gains a submission chapter and becomes count-agnostic (the seed invalidates its hard-coded 3-model counts).
effort: 3
dependencies: ["5.11", "5.15"]
---

# Step 5.16 — Grading map + demo-walkthrough submission chapter

**Effort: 3** — a mapping table plus a careful walkthrough edit, replayed
live.

Binding contract: `docs/roadmap/stage-01/phase-5/shared-knowledge.md` (D8). Prior
pin: the 4.10 landed decision — demo material extends
`docs/demo-walkthrough.md`; **no `demo-script.md` is created**. Agent:
**docs-writer**. Zero deviations — a deviation is a stop-and-report.

**Environment:** stack up with the **seeded** catalogue (5.11 run) — the
walkthrough is replayed against it.

## Outline

- New `docs/grading-map.md`: a table mapping each item of
  `docs/core-requirements.md` (RAG, ≥3 tools, domain specialisation,
  LangChain+OpenRouter, error handling/validation, UI: sources/tool
  results/progress) **and** each claimed bonus (hybrid search — the RRF
  retrieval; auth & personalisation — preferences; prompt-injection
  protection — `app/llm/fencing.py` + the fenced surfaces; Langfuse —
  config-gated, embeddings excluded; real-time KB updates — admin-triggered
  ingestion over SSE) to concrete files, endpoints and screens. Link it from
  README "Further reading".
- `docs/demo-walkthrough.md`:
  - Make the existing chapters **count-agnostic/seed-aware**: replace the
    hard-coded "3 approved models" counts and literal ULIDs with
    seed-tolerant wording ("at least the three original models …", "pick any
    approved model"); keep the price caveat (guessed values).
  - New **submission chapter**: register → CLI admin promote → add a new
    model to the backlog → watch ingestion progress → one **live admin
    review + approve** (the admin-verified story) → `app seed demo
    --auto-approve` note (bulk) → consultation interview → tool results,
    sources, recommendation cards → card click-through to the catalogue →
    filtered catalogue URL shared/reloaded → logout/login resume. Every
    grading criterion appears at least once; cross-reference grading-map
    rows.
- Update the walkthrough's replay stamp (HEAD + date) after replaying it.

## Verification

- The walkthrough replays green against the seeded stack, verbatim;
  grading-map rows point at real paths (spot-check each file/endpoint
  exists); README links to grading-map.

## Risks / notes

- Do not weaken the admin-verified claim: the live-review chapter is what
  earns it — auto-approve is explicitly labelled bulk convenience.
- Append (`### Step 5.16`) to `shared-knowledge.md` with the replay stamp —
  5.18 re-runs the walkthrough on a fresh clone.
