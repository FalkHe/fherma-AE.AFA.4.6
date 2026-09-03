---
phase: 5
step: "5.2"
title: Observability & polish (split — replaced by steps 5.9, 5.10, 5.13, 5.17)
summary: SPLIT. The former effort-8 observability/polish step was re-sliced (2026-08-28) into steps of max effort 4. See shared-knowledge.md for the binding contract and the mapping below.
effort: 0
dependencies: []
---

# Step 5.2 — Observability & polish (split)

**This step no longer exists as dispatchable work.** During the Phase-5
slicing (2026-08-28) its effort-8 scope was split, with the open design
points resolved and pinned in [`shared-knowledge.md`](shared-knowledge.md)
(decisions D5, D6, D9) and [`ui-spec.md`](ui-spec.md).

| Former 5.2 scope | Now lives in |
|---|---|
| Langfuse callback factory | 5.9 (D5 — `observability_callbacks` slot already exists; **embeddings excluded**, a documented limitation) |
| Langfuse Compose profile | 5.10 (D6 — dedicated `langfuse-postgres`, default stack byte-identical; bonus item, OQ-C) |
| Failure isolation (wrong `LANGFUSE_HOST` never fails a chat) | 5.9's verification |
| Progress-indicator audit | **Already landed and pinned** (Phase-2 §3 OperationProgress, Phase-3 TypingIndicator, Phase-4 §3.7/§4.6 states) — collapses to the ui-spec §2 audit matrix, gap closures in 5.13, QA spot-check in 5.17 |
| Empty states / loading skeletons | **Already landed per prior ui-specs**; the audited gaps (review tab panels, operations-query failure) close in 5.13 |
| "TanStack Query error boundaries with retry" | **Superseded by D9 / ui-spec §9**: per-screen EmptyState + refetch stays; one app-level `AppErrorBoundary` for render crashes (ui-spec §5) in 5.13 |
| "Reconnecting…" indicator | **Already landed** (`LiveConnectionAlert`, 5 s grace, "Live updates interrupted — reconnecting…") — no work; catalogue omission re-confirmed (ui-spec §9) |
| Re-embed job status | **Pinned deliberate omission** (ui-spec §3.7) — CLI-triggered job, the CLI is the progress surface; named in the 5.15 limitations |
| QA state-matrix walkthrough | 5.17 (M1) using ui-spec §2 as the checklist |
