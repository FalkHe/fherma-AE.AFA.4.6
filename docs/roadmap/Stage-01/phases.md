---
title: "Stage-01 — Phases"
stage: 1
version: 2
created: 2026-09-11
---

# Stage-01 — phases

Eleven phases in implementation order. Each states its **Goal** (what is true
when it is done), its **Preparation** (the investigation that must happen
before steps can be written), and its **Steps** (the work, one line each).

This is a rough plan. How anything is built — modules, routes, schemas,
payloads, file layout — is decided in the next planning level, when each phase
is written out, and by the implementing agents. Nothing of that belongs here.

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

**Depends on:** nothing. Parallel with phases 2 and 3.

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

## Phase 3 — Game Mechanics

**Goal:** Dice expressions parse and resolve deterministically, with a
visible/hidden distinction, and invalid input is rejected.

**Preparation:** Define the mechanics the game actually needs.

**Steps:**
- Decide the mechanic set and its architecture
- One step per mechanic
- Prove determinism by test

**Depends on:** nothing. Parallel with phases 1 and 2.

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

**Depends on:** phase 2. Parallel with phase 5.

---

## Phase 5 — Runs and Game State

**Goal:** A playthrough exists: it pins a content version, owns validated
object state and a scene position, records an append-only event stream with
cost, and is listable, archivable and resumable — all per owner.

**Preparation:** Investigate how run, progress, object state and events relate,
and what the ownership model is.

**Steps:**
- Decide the state and event model
- Implement runs and their lifecycle
- Implement object state with a validated write path
- Implement scene placement and advancing on an exit
- Implement the event stream with visibility filtering and cost accounting
- Enforce per-owner access

**Depends on:** phase 1. Parallel with phase 4.

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
