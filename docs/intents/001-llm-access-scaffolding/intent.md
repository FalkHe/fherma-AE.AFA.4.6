---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-15
stage: approved
source: docs/roadmap/Stage-01/phases.md (Phase 2)
milestone: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/milestones/2
---
# LLM Access and Prompt Scaffolding

Stage-01, Phase 2.

**Goal:** One provider seam carries chat, embedding and image calls with a
clear failure classification; prompt assets resolve by id; agent state
persistence is provisioned.

**Preparation:** Investigate provider capabilities and architect the AI
plumbing the later agents will sit on.

**Steps:**
- Decide and document the seam's shape and its failure classification
- Implement the seam for all three call kinds
- Implement prompt-asset resolution and pin where prompts live
- Provision agent state persistence
- Prove each call kind round-trips and each failure kind is distinguishable

**Depends on:** nothing. Parallel with phases 1 and 3.
