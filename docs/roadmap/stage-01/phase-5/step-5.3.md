---
phase: 5
step: "5.3"
title: Docs & demo readiness (split — replaced by steps 5.11, 5.15, 5.16, 5.18)
summary: SPLIT. The former effort-8 docs/demo step was re-sliced (2026-08-28) into steps of max effort 4. See shared-knowledge.md for the binding contract and the mapping below.
effort: 0
dependencies: []
---

# Step 5.3 — Docs & demo readiness (split)

**This step no longer exists as dispatchable work.** During the Phase-5
slicing (2026-08-28) its effort-8 scope was split, with the open design
points resolved and pinned in [`shared-knowledge.md`](shared-knowledge.md)
(decisions D7, D8).

| Former 5.3 scope | Now lives in |
|---|---|
| Seed model list + `app seed demo --auto-approve` | 5.11 (D7 — skip-if-exists in any status; same pipeline, no status bypass; report-and-continue) |
| README (quickstart, prerequisites, CLI reference, Langfuse profile) | 5.15 (README **extended**, not rewritten — most of it landed in earlier phases) |
| "`.env.example`" | **Superseded**: the template is and stays **`.env.dist`** (README/compose already reference it); 5.9 keeps it in lockstep with `config.py` |
| "Demo script `docs/demo-script.md`" | **Superseded by the 4.10 landed decision**: 5.16 extends `docs/demo-walkthrough.md` (submission chapter + count-agnostic rewrite of the seed-invalidated model counts) |
| Grading-criteria map `docs/grading-map.md` | 5.16 |
| Limitations & improvements section | 5.15 (list pinned in D8) |
| Fresh-clone verification | 5.18 (M3 acceptance; tags `phase-5-done`) |
