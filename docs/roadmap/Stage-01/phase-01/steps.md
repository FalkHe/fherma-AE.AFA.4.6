---
title: "Stage-01 Phase 1 — Adventure Content — steps"
stage: 1
phase: 1
created: 2026-09-11
---

# Phase 1 — Adventure Content — steps

Four steps — three that built the phase, and **step 1.4, a rework taken after it
landed**. Each states its **Goal** (what is true when it is done), whether it
is **human in the loop**, its **Steps** (the work, one line each) and what it
**depends on**.

How anything is built — the module, the models, the fields, the rules, the
command, the file layout — is already pinned one level down in
[shared-knowledge.md](shared-knowledge.md), and is restated nowhere here.

Phase 1 ends with nothing a player can see. Its capability is surfaced by
phase 7 (the run a player starts against this content) and phase 8 (the DM
reading scenes and creatures).

---

## Step 1.1 — The content module

**Goal:** A hand-authored content tree loads into typed objects, every schema
and referential problem in it is reported in one pass, and a command-line check
passes a correct tree and fails a broken one with a distinguishable exit code.

**Human in the loop:** no.

**Steps:**
- Implement the content schema and the version-pinned tree layout
- Implement the loader over one campaign version, serving whole and single-entity reads
- Implement the referential rule set on top of the loaded objects, collecting every problem
- Expose the same validation path as a command-line check with its own exit codes
- Register the command in the shared command surface with a single additive block
- Write the module's own short readme

**Depends on:** nothing. Parallel with step 1.2.

---

## Step 1.2 — The authoring guide and the documents this phase invalidates

**Goal:** A schema reference exists that an agent could author a conformant
campaign from alone, the documentation index lists it, and every general
document this phase contradicts has been corrected.

**Human in the loop:** no.

**Steps:**
- Write the schema reference: layout, versioning, every field, every rejecting constraint, the rule set, a worked example of each file kind
- State in it the two rules a generator gets wrong by default: a scene is facts and consequences, never a script; an exit condition is prose, never a flag
- Add the module's row to the documentation index
- Apply the corrections this phase owns to the general design and requirement documents

**Depends on:** nothing. Parallel with step 1.1. Both must land before step 1.3.

---

## Step 1.3 — The first campaign

**Goal:** One campaign — one adventure, at least three scenes, its definitions
and a seed player character — is authored from the guide alone, the command-line
check passes over the shipped tree, and the suite proves the shipped tree loads
and reads back unmocked.

**Human in the loop:** yes. The owner picks the subject, reads the prose and
accepts or rejects it; nothing validates prose quality.

**Steps:**
- Author the campaign against the guide, not against the implementation
- Reach a terminal scene from the entry scene, and make every scene reachable
- Include a creature that can fight and one that cannot, so both shapes are exercised
- Prove the shipped tree passes the command-line check and loads unmocked in the suite
- Record any guide defect the authoring exposed, in the guide

**Depends on:** steps 1.1 and 1.2. Parallel with nothing.

---

## Step 1.4 — The object-template rework

**A rework of steps 1.1–1.3, not new ground.** Four owner decisions taken after
the phase landed — items and fixtures get authored templates, the entity is
renamed, the templates move into the campaign file, and a placement may carry
things at spawn — are applied to the schema, the loader, the rule set, the
shipped campaign and the authoring guide.

**Goal:** A scene declares creatures, items and fixtures alike; each kind is
validated against exactly the fields its mechanics need; a placement can own
equipment at spawn; the campaign version is two kinds of file; and the shipped
campaign still passes the command-line check with its Story unchanged.

**Human in the loop:** yes, once — the owner accepts the new object templates'
prose by approving the step spec, not during implementation.

**Steps:**
- Replace the single creature entity with a kind-discriminated template union
- Move the campaign-scoped templates into the campaign file and retire the third file kind
- Add the carried-at-spawn placement axis and the rules that keep it one level deep
- Rework the referential rule set to eighteen rules over in-memory templates
- Migrate the shipped campaign without touching a word of its Story
- Rework the authoring guide and the glossary to the landed contract

**Depends on:** steps 1.1, 1.2 and 1.3, all landed. Backend-only — no frontend
surface exists for this module.
