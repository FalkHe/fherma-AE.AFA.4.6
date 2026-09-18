---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-17
updated: 2026-09-17
stage: approved
source: docs/roadmap/Stage-01/phases.md (Phase 5)
milestone: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/milestones/5
---
# Game State Services

Stage-01, Phase 5.

**Wish:** Every change to game state goes through a validated service.

**Goal:** Every change to game state goes through a named mechanic in one
service module, and the DM has no other way to change anything. A campaign run
starts, gets its character, lists, opens, archives, unarchives and resumes;
adventures are entered explicitly; objects change only through mechanics that
take object ids and roll-result ids — attack, damage, interact, take, drop, give,
use an exit — never a number the agent typed; events append with their
visibility, and cost is a sum over them; dice are derived from kind and actor,
rolled by the server, visible or hidden, recorded as events and consumed at
most once. Access is per owner throughout, and nothing edits a state row any
other way.

**Preparation:** Define the mechanics the game actually needs and name the
state transition each one is. A mechanic that changes nothing is arithmetic
inside the service that records its result, not a service of its own — so this
preparation produces a list of transitions, not a layer.

**Steps:**
- Decide the mechanics surface: one service function per state change, and the
  roll-result contract they share (→ `decisions/mechanics.md`)
- Implement the run lifecycle: start in `setup`, create the character (→ `ready`), first
  narration (→ `active`), enter an adventure explicitly, archive / unarchive, finish on the last ending exit
- Implement dice — formula derivation by kind and actor, RNG behind a seam,
  visible / hidden — inside the transition that records the roll, plus the
  roll-request / roll-click pair and single consumption
- Implement the mechanics: checks, interact, inventory moves, attack and damage
  (events-only combat), `use_exit` for scene change and adventure end
- Implement the event append path with visibility filtering and cost accounting,
  the events read and the SSE `updated` signal
- Enforce per-owner access
- Prove determinism, single consumption and one action per turn by test

**Depends on:** phase 3 — a service that changes state needs the state.
Parallel with phase 4.

**Research note:** the state model is under construction in phase 3. Research
the model from intent `003-game-state` (its `decisions.md` and
`decisions/model.md`), not from the codebase or the database.
