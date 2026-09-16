---
title: "Stage-01 — Phases"
stage: 1
version: 3
created: 2026-09-11
---

# Stage-01 — phases

Eleven phases in implementation order. Each states its **Goal** (what is true
when it is done), its **Preparation** (the investigation that must happen
before steps can be written), and its **Steps** (the work, one line each).

This is a rough plan. How anything is built — modules, routes, schemas,
payloads, file layout — is decided in the next planning level, when each phase
is written out, and by the implementing agents. Nothing of that belongs here.

**Numbers 3 and 5 were reassigned in version 3.** Game state is now built in
two phases — the model and its tables (3), then the services that change them
(5) — because a mechanic is a state transition and cannot be built or tested
before the state it acts on exists. The former "Game Mechanics" phase is
dissolved into phase 5: dice are arithmetic over a roll that gets recorded, not
a layer of their own. Phases 1, 2 and 4 keep their numbers and their scope.
**An older document saying "phase 5" means today's phase 3 where it speaks of
tables, columns, entities or the ownership model, and today's phase 5 where it
speaks of lifecycle, writes, advancing or accounting; "phase 3" in an older
document means dice, which is today's phase 5.**

---

## Phase 1 — Adventure Content

**Goal:** A content schema exists and one campaign (1 adventure, ≥3 scenes, a
starting character) is authored against it, loadable and validated.

**Preparation:** Investigate a robust data model for adventure content.

**Steps:**
- Implement the schema
- Document the schema so a generating agent could fulfil it
- Implement validation / verification
- Author the first campaign against it (human in the loop)
- Prove the authored set is valid and readable

**Depends on:** nothing. Parallel with phase 2.

---

## Phase 2 — LLM Access and Prompt Scaffolding

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

---

## Phase 3 — Game State

**Goal:** The state of a playthrough exists as real tables: a run that pins a
content version and belongs to an owner, its position in the adventure, the
objects instantiated from the content's definitions with their promoted stats,
the per-run settings, and an append-only event stream with room for visibility
and cost. Every table is reachable by migration and round-trips a read.

**Preparation:** Settle the business model — what a run, its progress, an
object and an event are, how they relate, and who owns a run — then pin the
data model onto it. This is the phase that closes the model's open decisions;
it does not defer them to whoever writes the first service.

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

---

## Phase 4 — SRD Knowledge Base

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

**Depends on:** phase 2. Parallel with phases 3 and 5.

---

## Phase 5 — Game State Services

**Goal:** Every change to game state goes through a service that validates it.
A run starts, lists, opens, archives, unarchives and resumes; objects change
only through a validated write path that rejects an illegal write; a scene
advances on an exit; events append with their visibility, and cost is a sum
over them; dice parse and resolve deterministically, visible or hidden, as part
of recording the roll. Access is per owner throughout, and nothing edits a
state row any other way.

**Preparation:** Define the mechanics the game actually needs and name the
state transition each one is. A mechanic that changes nothing is arithmetic
inside the service that records its result, not a service of its own — so this
preparation produces a list of transitions, not a layer.

**Steps:**
- Decide the service surface and which mechanic belongs to which transition
- Implement the run lifecycle
- Implement the validated object write path, rejection included
- Implement scene placement and advancing on an exit
- Implement the event append path with visibility filtering and cost accounting
- Implement dice — expression parse, RNG, visible/hidden — inside the
  transition that records the roll
- Enforce per-owner access
- Prove determinism and rejection by test

**Depends on:** phase 3 — a service that changes state needs the state.
Parallel with phase 4.

---

## Phase 6 — Journal Memory

**Goal:** Facts are written and embedded during play and retrieved later by
similarity plus unconditional recency.

**Preparation:** Decide what a journal entry is and what the retrieval policy
is. The DM writes the journal itself through a tool — no separate chronicler
agent, no second writer.

**Steps:**
- Implement the write path with embedding
- Implement retrieval
- Decide and implement the mitigation for re-injected player-derived text
- Prove semantic recall and recency recall separately

**Depends on:** phases 2 and 5. Parallel with phase 7.

---

## Phase 7 — Character Creation

**Goal:** A player describes a character in plain words, answers a follow-up or
two, and receives a finished sheet with a portrait, landing in a run they can
list, archive and resume. This is the first player-visible milestone.

**Preparation:** Investigate the dialogue shape, the human-in-the-loop
mechanism, and the portrait pipeline.

**Steps:**
- Build the character generation agent and its prompt
- Pin the interrupt / resume convention
- Add portrait generation with a deterministic fallback
- Build the app shell and the playthrough browser
- Build the character creation screen and the character sheet display
- Ensure a run cannot be reached without a character

**Depends on:** phases 2 and 5. Parallel with phase 6.

---

## Phase 8 — The DM Turn

**Goal:** A turn runs end to end: free text in, streamed narration out; the DM
reads scene and monster facts, rolls real dice, writes validated state,
advances scenes, cites rules, uses the journal, asks the player when the choice
is theirs, and refuses injection and out-of-band state claims. Turns are
recorded with cost and a failed turn is recoverable.

**Preparation:** Investigate the agent loop, the tool set it needs, and the
streaming transport.

**Steps:**
- Build the DM agent loop
- Bind the tools it needs (scene, monster, dice, state, rules, journal, ask player)
- Write the system prompt and the personality fragments
- Build the guard against injection and out-of-band state claims
- Build the streaming turn transport with progress milestones
- Record per-turn events and cost
- Handle turn failure and retry

**Depends on:** phases 1–7. Parallel with nothing.

---

## Phase 9 — The Play Screen

**Goal:** The player plays in a browser — narration, live character state, a
filtered trace of rolls, citations, retrievals, refusals and cost, decision
prompts, retry — with hidden rolls never surfacing.

**Preparation:** Design the screen and its states.

**Steps:**
- Build the play screen frame, narration pane and composer
- Build the trace pane and its renderers
- Make the character state display live
- Add the journal view
- Add the decision prompt and the retry affordance
- Make it work on a small screen

**Depends on:** phase 8.

---

## Phase 10 — Developer Drawer

**Goal:** Model, temperature, personality and a marked free-text prompt
override are changeable per run, in a surface the player experience does not
contain; the drawer also shows the effective prompt and the pinned content
version read-only.

**Preparation:** Decide what the override is allowed to do, given the guard.

**Steps:**
- Build the drawer and the run-settings write path
- Expose the model and personality catalogues
- Show the composed prompt and content version read-only
- Settle the override policy against the guard
- Keep all of it out of the player UI

**Depends on:** phases 5, 8 and 9.

---

## Phase 11 — Release

**Goal:** Chat-model calls are traceable when tracing is enabled, and a
stranger can run and understand the agent from the documentation alone.

**Preparation:** Review what the earlier phases already documented, and what is
missing.

**Steps:**
- Wire tracing into the provider seam
- Complete the module documentation and the docs index
- Write the tool reference and the content authoring guide
- Write usage and worked examples
- Correct the general docs the stage invalidated
- Prove a fresh checkout reaches a named end state following the docs alone
