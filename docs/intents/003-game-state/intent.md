---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-16
stage: approved
source: docs/roadmap/Stage-01/phases.md (Phase 3)
milestone: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/milestones/12
---
# Game State

Stage-01, Phase 3.

**Wish:** Define and craft the business and data model required for the
playthrough.

**Goal:** The state of a playthrough exists as real tables: a run that pins a
content version and belongs to an owner, its position in the adventure, the
objects instantiated from the content's definitions with their promoted stats,
the per-run settings, and an append-only event stream with room for visibility
and cost. Every table is reachable by migration and round-trips a read.

**Preparation:** Settle the business model — what a run, its progress, an
object and an event are, how they relate, and who owns a run — then pin the
data model onto it. This phase closes the model's open decisions; it does not
defer them to whoever writes the first service.

**Steps:**
- Decide the business model: run, progress, object state, event, settings, and
  the ownership model
- Pin the data model onto it and place it in modules
- Implement the run, its content-version pin and its progress
- Implement object state, with the stats promoted to columns
- Implement the event stream and the per-run settings store
- Land the migration and prove each table round-trips a read
- Correct the general docs this model invalidates

**Depends on:** phase 1 — objects are instantiated from content definitions, so
the schema has to exist first. Parallel with phase 2.
