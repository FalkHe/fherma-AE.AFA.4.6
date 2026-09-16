---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-15
stage: approved
source: docs/roadmap/Stage-01/phases.md (Phase 4)
milestone: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/milestones/4
---
# SRD Knowledge Base

Stage-01, Phase 4.

**Goal:** SRD 5.1 is ingested and embedded, and a rules query returns relevant
passages with citable references.

**Preparation:** Investigate the source data and decide the target structure of
the embeddings.

**Steps:**
- Gather the source data (document a manual route, or script a fetch)
- Build ingestion, chunking and embedding
- Run the ingestion and check the result
- Provide the retrieval service
- Handle re-ingestion and the empty-corpus case

**Depends on:** phase 2. Parallel with phases 3 and 5. Phase 2 (LLM Access and
Prompt Scaffolding) has landed.
