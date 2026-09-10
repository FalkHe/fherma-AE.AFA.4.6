---
title: "Stage-01 — phases"
stage: 1
created: 2026-09-10
---

# Stage-01 — phases

One section per phase. The stage-level contract — capability inventory,
classification, dependency graph, scope fence, registers — is
[README.md](README.md); this file is the per-phase detail.

Each section states the phase's **Milestone** as shipped functionality, the
capabilities it lands, **what a reviewer can see working**, what it pays into,
its dependencies and parallelism, the open decisions and doc corrections it
owns, and any constraint it inherits. **No steps, no routes, no columns, no
payload shapes** — those are the step specs' business, and the phase
directories that hold them arrive with each phase.

Reading order note: "sees working" is the evidence a reviewer can produce
themselves. For phases 1–3 that evidence is a command, not a screen, for the
reason given in [README.md](README.md) §7.

---

## Phase 1 — Content foundation

**Milestone.** One campaign, one adventure, at least three scenes and a pregen
player character exist as validated JSON in git, each adventure carrying an
authored prose `intro`; the set is loadable at a pinned content version and is
**present and readable in the content read surface**.

**Capabilities landed.** Content Schema & Loader (backend module `content`);
the Authored Content Set, **including the pregen player character**; the
Content Validation CLI.

**What a reviewer sees working.**

- The validation command passes on the shipped set.
- A deliberately broken exit reference or an unknown definition id produces a
  precise, located error — content integrity is loader-enforced, so this is
  the only place a typo is ever caught.
- A scene, an adventure's `intro`, and the pregen player character, each
  printed by id at a pinned version.
- The campaign present and readable in the read surface's response.

**Pays into.** Requirement 2 (the content layer) and "a relevant knowledge
base for their domain". This is also where
[README.md](README.md) §7's player-capability reading of requirement 3 is
first stated.

**Dependencies.** Phase 0 only. Content is hand-authored, so no model is
needed. **Parallel with 2** (group A).

**Open decisions owned.** None.

**Doc corrections owned.** `general/architecture.md`'s "authored by an LLM
once through a `generate_adventure` CLI" sentence; `general/model.md`'s
description of the content shape, to include both `intro` and the pregen player
character;
`general/requirement-map.md`'s requirement-3 wording; the first
`docs/modules/` entry and the corresponding `docs/README.md` row.

**Inherited constraints.**

- The milestone claims only that the content is **present and readable**, which
  is exactly what the evidence above proves. It deliberately does not claim the
  campaign is "startable" or "playable": starting is phase 4's verb and playing
  is phase 5's, and borrowing either would make this phase's milestone
  unverifiable by its own evidence.
- **The pregen player character is content, not scaffolding.** Phase 4's state
  pane has a character to show only because this phase ships one, and phase 8
  turns it into an explicit quick-start rather than deleting it.
- The authored `intro` is **not scaffolding**. Without it, phase 4's first
  visible screen could only render a scene's authored facts and intentions,
  which read as a design document and break "the player never has to know the
  rules" on the very first screen. It stays the DM's opening beat forever.
- **No screen.** Surfaced to the player by **phase 4** (the campaign picker
  and the intro on the first screen) and **phase 6**.

---

## Phase 2 — LLM gateway & prompt assets

**Milestone.** The app talks to a model through OpenRouter via LangChain, and
the DM's effective prompt is a composed, inspectable artefact. Two named
commands are the milestone: one prints the composed effective prompt for a
given personality and override, the other runs one prompt end to end and
prints the response together with its token and cost figures. The LangGraph
checkpointer's schema is provisioned and excluded from Alembic.

**Capabilities landed.** The LLM Gateway (`core/` singleton) — **the single
OpenRouter seam, chat side**, which phase 3 extends rather than duplicates;
Prompt Composer;
Prompt Assets — the base DM prompt and at least two personality fragments;
the settings promotion for the OpenRouter key, chat model, embedding model and
embedding dimension; the LangChain, LangGraph and checkpointer dependency
additions; Checkpointer Provisioning plus the Alembic exclusion of the
checkpointer's schema.

**What a reviewer sees working.**

- Both named commands, by name.
- A bad key and a request timeout each failing cleanly and
  **distinguishably** — one is a configuration fault, the other is a runtime
  one, and conflating them is the phase-0 `unwrap()` mistake repeated on the
  backend.
- The composed prompt visibly changing with the personality id, and again with
  an override.
- `alembic upgrade head` → `downgrade base` → `upgrade head` round-tripping
  against a fresh database with the checkpointer's schema present and
  untouched — a stray autogenerate must not try to drop it.

**Pays into.** Requirements 2 and 4; groundwork for Easy-2, Easy-3 and
Easy-4, which phase 9 banks.

**Dependencies.** Phase 0 only. **Parallel with 1** (group A).

**Open decisions owned.**

- Where the cost figure comes from — a static price table in settings, or
  OpenRouter's usage-accounting field. Decided here because phase 5 renders it
  and a wrong number is worse than no number. **Trap to know before speccing:
  the static-table branch needs new declared settings that `.env.dist` has no
  entries for, and `.env.dist` is owner-only** — that branch cannot be taken
  without an owner edit.
- **The failure-injection seam**: how a provider failure is produced on demand
  — an unreachable base URL, a bogus model id, an injected timeout. A bad key
  is producible by editing `.env`, but phase 5's timeout evidence and phase 8's
  image-failure evidence are not, and the drawer that could otherwise stand in
  arrives after both. **This phase defines one seam and phases 5 and 8 reuse
  it**, rather than each inventing its own.

**Doc corrections owned.** `general/model.md`'s static-file tree, which must
not list a content-generation prompt asset; `general/backend-stack.md`'s claim
that LangChain and LangGraph are already declared; **D7's first amendment** in
`roadmap/phase-0/shared-knowledge.md`.

**Inherited constraints.**

- **Prompt scope.** The system prompt instructs plain language and requires
  the DM to self-explain any game term it uses. This is the mitigation for the
  i18n carve-out leaving narration prose unannotated: if the copy cannot be
  curated, the instruction that produces it must be.
- The checkpointer's provisioning lands here rather than in phase 5, so the
  critical-path phase does not carry a migration-shaped risk inside its
  feature work.
- **This phase lands the chat side of one seam, not a chat-only gateway.** The
  credential lives here, failures are classified here, and phase 3 adds the
  embedding side to the same seam. A second OpenRouter client anywhere would be
  a second credential site and a second failure-classification site.
- **No screen.** Surfaced by **phase 5** (the prompt drives the narration) and
  **phase 9** (the drawer shows the composed prompt read-only).

---

## Phase 3 — SRD knowledge base

**Milestone.** SRD 5.1 is ingested into pgvector, and a rules question returns
relevant passages with citable section references.

**Capabilities landed.** pgvector enablement; **the embedding side of the LLM
Gateway** — an extension of phase 2's single OpenRouter seam in `core/`, not a
new file and not a candidate for a later promotion; the SRD Rule Ingestion CLI;
the Rule Lookup service.

**What a reviewer sees working.**

- An ingest run reporting its counts.
- A query command answering a real rules question with its cited sections.
- A re-ingest replacing the corpus wholesale — an SRD rule is owned by nobody
  and is rebuilt, never migrated.
- A query against an empty corpus failing cleanly rather than returning
  nothing indistinguishable from a miss.

**Pays into.** **Hard-1**, the corpus half. Phase 10 banks it.

**Dependencies.** Phase 2. **Parallel with 4** (group B) — disjoint modules,
but **not disjoint Alembic revisions**: this phase owns the pgvector
migration, and its revision order against phase 4's must be agreed before
either is dispatched. See the inherited constraint below.

**Open decisions owned.**

- Whether LangChain's OpenAI-compatible embeddings class can be pointed at the
  OpenRouter base URL, and so whether the embedding side of the seam is a
  configuration of that class or a thin call of its own. **Use `mcp__context7`
  when this phase is specced; do not answer it from recall.**
- **How the migration expresses the vector width — and only that.** `.env.dist`
  already pins `EMBEDDING_MODEL`, states that its native size is 1536, states
  that no `dimensions` parameter is ever sent, and requires a migration to
  change it. Nothing about the model is open here, and **this phase must not
  pick a different embedding model: `.env.dist` is owner-only.**
- **How** a fixture-local real engine is driven — not whether one is allowed,
  which `backend-stack.md` already permits. The narrower problem is that doing
  it against async SQLAlchemy collides with the landed "fully synchronous
  suite, no `pytest-asyncio`, no async fixtures" rule, so this phase may have
  to **amend a landed decision** rather than merely make one. Similarity search
  is inherently database-bound, so it cannot be deferred, and `qa-backend`
  needs the policy pinned rather than improvised.

**Doc corrections owned.** Conditional on the decision above: if a
fixture-local async engine is needed, the "fully synchronous suite" rule in
`general/backend-stack.md` and phase 0's shared knowledge is amended here, not
worked around.

**Inherited constraints.**

- **No screen.** Surfaced by **phase 10**.
- **The revision chain is linear.** This phase and phase 4 run in parallel and
  would otherwise stack revisions on the same `down_revision` while both adding
  a line to `alembic/env.py`. The two are assigned an explicit revision order
  and the later rebases onto the earlier one's head; the hazard is the heads,
  not the migration content.

---

## Phase 4 — Playthrough & character state

**Milestone.** A player starts a run of the shipped campaign, sees it listed,
opens it, reads the adventure intro, inspects a character sheet with its terms
explained, archives and unarchives it, and reloads to resume where they left
off.

**Capabilities landed.** Playthrough Lifecycle and the per-run settings store;
**initial scene placement** — the active adventure, and the character starting
in the entry scene; the Object State Models and their read surface; the
instantiation of phase 1's pregen player character; App Shell & Navigation; the
Playthrough Browser; the play-screen frame; the narration pane rendering the
intro; the state pane; the term-explanation pattern.

**What a reviewer sees working.**

- In the browser: start → list → open → archive → "show archived" →
  unarchive with a confirm → reload and resume.
- Several concurrent playthroughs coexisting in the list.
- The state pane populated from the pregen character, with its terms explained
  where they appear.
- A second user unable to see the first user's run — authorisation is
  ownership, and this is the first phase where there is anything to own.
- The run-total cost slot present on the list row and in the play-screen
  header, reading zero, because nothing has cost anything yet.

**Pays into.** Requirement 3; Medium-4's personalisation half on top of the
landed authentication.

**Dependencies.** Phase 1. **Parallel with 3** (group B).

**Open decisions owned.** All three data-model questions the roadmap
deliberately does not pin: ownership of a run (a membership row or a user id);
the adventure's progress (its own entity or fields on the run); and whether
the object state models and read surface are their own module or a service
inside `playthrough`.

**Doc corrections owned.** Every combat-removal correction:
`general/model.md`'s combat paragraph, the encounter node in the entity
diagram, "Encounter hangs off AdventureRun" and the encounter line in the
lifecycle table; `general/glossary.md`'s **Encounter** entry and its
**Initiative** game term, which now has no caller;
`general/app-vision.md`'s "turn order beside the narration";
`general/architecture.md`'s "state panel (HP, AC, inventory, turn order)".

The rest of `general/model.md`'s lifecycle table comes with it, since this
phase already owns that table: the **Purge** row describes a capability
Stage-01 fences out, and "generate the player's creature" on starting a
playthrough is now phase 1's pregen, which phase 8's agent later replaces.
`general/glossary.md` gains a term for the **pregen player character**, because
nothing currently names the thing phase 8 turns into a quick-start.

**And two conditional corrections that must be resolved either way.**
`general/model.md` writes "ownership lives on the membership row" as a *ruling*
and `general/architecture.md` repeats it; `general/model.md` writes
`AdventureRun` as a full entity with its own justification. This roadmap
records both as **open decisions**. If this phase overturns either, it corrects
those files; if it upholds either, it records that the decision is closed.
**A phase-4 architect must not be left reading two documents that disagree
about whether there is a choice.**

**Inherited constraints.**

- This phase ships the state **models and read surface only**. The validated
  write path is **phase 6's**, because a validator with no writer is
  speculative and cannot be proven without a synthetic caller.
- **Scene placement, not scene progression.** This phase places the character
  in the entry scene; **advancing on an exit is phase 6's**, with the validated
  write path, because position is object state and advancing it is a validated
  write. Landing the advance here would repeat exactly the mistake the previous
  bullet avoids — a writer with nothing to write about.
- **The app-shell promotion is conditional.** The shell graduates from
  `modules/home` to `src/components/` only if it keeps its
  `action?: ReactNode` slot pattern and **imports from no module**, per D1's
  worked example. This phase adds navigation, which is exactly where sign-out
  and current-user creep in; if they do, the shell has not earned the promotion
  and stays where it is.
- This phase adds the **second protected route**, and therefore owns the
  phase-0 `useSignIn` fix: its success handler must **navigate first and write
  the `["currentUser"]` cache after**, or `RequireAnonymous` wins the race and
  the user lands on `/` instead of where they came from. Recorded in phase 0's
  known future work; do not rediscover it as a bug.
- **Archive UX is ruled**: a "show archived" filter plus an explicit unarchive
  with a confirm dialog. No timed undo.
- **The content version is invisible to the player.** It appears read-only in
  the drawer (phase 9) and nowhere in player chrome.

- **The revision chain is linear.** This phase and phase 3 run in parallel and
  would otherwise stack revisions on the same `down_revision` while both adding
  a line to `alembic/env.py`. The two are assigned an explicit revision order
  and the later rebases onto the earlier one's head.

**Surfaces created here, and the phases that extend them.** Playthrough list
→ 8, and 5/6. Play-screen frame → 5, 9, 11. Narration pane → 5, 7. State pane
→ 6, 8. Term-explanation pattern → 6.

---

## Phase 5 — The DM turn loop

**Milestone.** The player types what their character does in plain words and
the AI Dungeon Master narrates, streamed, with agent-progress milestones as it
works. The DM reads scene facts and stat blocks through `get_scene` and
`get_monster`. The turn is recorded as events with its cost, history survives
a reload, and a failed turn is recoverable and does not eat the input.

**Capabilities landed.** The Dungeon Master Agent — the LangGraph loop over
the checkpointer; the tool set `get_scene` and `get_monster`; the Turn
Transport (SSE carrying narration and progress milestones); the Event Stream
and Cost Accounting (backend module `events`); Turn Failure & Recovery; the
trace pane; the composer; the failure and refusal pattern.

**What a reviewer sees working.**

- A real turn, end to end, in the browser.
- Progress milestones arriving while the turn is in flight.
- Trace-pane rows carrying each turn's cost, with the run total in the
  play-screen header and on the list row.
- A reload replaying the run's history.
- A forced model failure terminating the stream with the error object,
  preserving the typed input and offering a retry.
- A **completed** turn carrying no retry affordance at all.

**Pays into.** **Medium-1 banked** — cost is summed from the event stream, per
turn on the trace row and per run in the header. **Medium-2's short-term
half** via the checkpointer. Requirements 2, 3 and 4.

**Dependencies.** Phases 1, 2 and 4. **Parallel with nothing** — this is the
critical-path phase, and everything before it exists to keep it small.

**Open decisions owned.**

- The agent-progress milestone vocabulary. See the constraint below: it is
  bound in advance, not discovered later.
- The in-stream error representation. **Ruled: one error shape, two
  transports** — a turn that fails after the 200 terminates the stream with an
  event carrying the same `{code, message, details}` object, so D4's single
  shape holds even though the transport differs. This phase pins the remaining
  transport detail.
- The residual i18n wording. **Ruled: agent-authored content — narration,
  citations, option labels, journal facts — is verbatim model output and is
  exempt from the i18n-key rule.** Open only in how
  `general/frontend-stack.md` expresses it, which is the doc correction below.

**Doc corrections owned.** `general/architecture.md`'s wire convention, which
gains SSE as a third response kind — **and must state affirmatively that D5 is
not amended**, because a long-lived SSE response is still one request, so
"request-scoped or a CLI one-off" still holds and nobody should read the
streaming ruling as breaking it. Also `general/architecture.md`'s tool table,
losing its `start_combat()` / `end_round()` rows; and
`general/frontend-stack.md`'s i18n section, which currently says every
user-facing string goes through a key with no carve-out for verbatim model
output.

**Inherited constraints.**

- **The milestone vocabulary is bound by phase 6's hidden-roll constraint,
  here and now, not as a phase-6 discovery.** Phase 6 ships hidden rolls that
  the client never sees; the vision says the fact that a roll happened is not
  a tell. A "rolling…" milestone during a hidden check is exactly that tell.
  Either milestones are emitted only for visible actions, or the vocabulary is
  coarse enough not to distinguish — decided in this phase's spec, before the
  wire contract is written.
- **The trace pane is pinned as typed rows rendered from one filtered event
  stream**, so phases 6, 7, 10 and 11 each add a renderer and nothing else.
  Five phases touch this surface; it is the highest-churn thing in the stage.
- **Prompt scope.** With no dice yet, the DM narrates and **defers** rather
  than handwaving an outcome it has no way to determine. The system prompt
  also instructs plain language and self-explanation of any game term used
  (carried from phase 2).
- **No turn cancel.** Retry exists for a failed turn only.
- **Cost is player-facing.** It belongs on the trace row and in the header,
  not behind the developer fence.
- **Play stays within the entry scene.** Advancing on an exit is phase 6's,
  which is consistent with the narrate-and-defer constraint above: with neither
  dice nor a validated write path, the DM has no way to resolve leaving a room.
- **The player's free-text turn input carries a length cap**, enforced server
  side. It is the only control standing between free text and a tool-calling
  loop until phase 7, and an uncapped field is both a cost and a
  prompt-injection surface.
- **This phase and phase 6 knowingly ship a free-text-into-tool-calling loop
  with no guard.** The guard arrives in phase 7, so the mitigation for two
  phases is the input cap plus *scheduling*, and nothing else. Stated plainly:
  neither phase is a deployable state, and phase 7 is not droppable.
- **The timeout evidence above uses phase 2's failure-injection seam.** This
  phase does not invent its own way to produce a provider failure.

**Surfaces created here, and the phases that extend them.** Trace pane → 6, 7,
10, 11. Composer → 7. Failure / refusal pattern → 7.

---

## Phase 6 — Real dice, real consequences

**Milestone.** Actions resolve on visibility-aware dice against real target
numbers, consequences land in validated state, and the player watches hit
points change. The character advances between scenes on an exit. The outcome
of a hidden roll changes the narration and **no roll row appears for it**.

**Capabilities landed.** Dice & Mechanics as pure functions inside `game`;
the `roll_dice` and `update_object` tools; the Validated State Writes path,
**and with it the scene advance** — moving the character on an exit, because
position is object state;
the roll-row trace renderer; the state pane's change affordance; the
term-explanation pattern extended to the terms rolls introduce.

**What a reviewer sees working.**

- A check resolved with a visible roll row — expression, result, target — and
  the state pane's hit points changing as a consequence.
- A hidden-roll turn whose narration reflects a real outcome with **no roll
  row**. That is the browser-visible half of the milestone; the payload-level
  assertion that a hidden roll never reaches the client stays a QA criterion,
  because a reviewer cannot see the absence of a field.
- An invalid dice expression rejected specifically and recorded as an error
  event — the audit trail survives the failure.
- An invalid state write rejected. Without this, the "deterministic mechanics"
  layer is decoration.
- The character **moving to another scene on an exit**, and the narration
  following it there. Phase 4 placed the character; this is where it can leave,
  because leaving is a validated write of its position.

**Pays into.** Requirement 4, and the vision's "the dice are real" principle —
outcomes come from actual rolls against actual target numbers.

**Dependencies.** Phase 5. **Recommended before 7**, and 7 may run in parallel
if the graph and tool-registry seam has a single owner.

**Open decisions owned.** None.

**Doc corrections owned.** None — phase 5 removed the combat tool rows and
phase 4 the rest.

**Inherited constraints.**

- **Prompt scope.** With combat out of Stage-01, a fight resolves in one or
  two rolls and their consequences, never as simulated rounds. The prompt must
  say so, because a model given dice and monsters will otherwise invent an
  initiative order the system cannot track.
- Adds exactly **one trace renderer** against phase 5's pinned row contract.

**Surfaces extended.** Trace pane, state pane, term-explanation pattern,
playthrough list.

---

## Phase 7 — Human-in-the-loop & the guard

**Milestone.** The DM asks when the decision is the player's, the interrupt
survives a reload, and prompt injection and out-of-band state claims are
refused legibly.

**Capabilities landed.** The `ask_player` tool and the interrupt; the Guard;
the decision-prompt affordance in the narration pane; the composer's
decision-response mode; the refusal pattern; the trace renderers for
interrupts and refusals.

**What a reviewer sees working.**

- A turn that stops on a decision and presents its options.
- A reload that returns to the same pending decision — the interrupt is
  durable, not a client-side state.
- "My HP is 100" refused with an explanation and **no state change**.
- A prompt-injection attempt refused, with the refusal visible in the trace so
  the player can see the system defended itself rather than silently ignoring
  them.

**Pays into.** **Medium-8's guard half** — phase 9 banks the other half.
Requirement 2's "necessary user interactions", which is the whole point of an
interrupt rather than a monologue.

**Dependencies.** **Build: phase 5 only.** Interrupts and the guard attach to
the graph and the stream; neither reads a die roll or an object patch.
**Demo: phase 6.** The "refused with **no state change**" criterion above is
vacuous before phase 6, because until then there is no state a turn could have
changed — so the criterion is only meaningful once 6 has landed, even though
this phase compiles and passes its own tests without it.

**Open decisions owned.** None.

**Doc corrections owned.** `general/requirement-map.md`'s "`ask_player`
**every turn**", which contradicts this phase's milestone: the DM asks when the
decision is the player's, and one that asked every turn would not be
narrating.

**Inherited constraints.**

- **Phases 6 and 7 may be parallelised only if the graph and tool-registry
  seam is assigned to a single owner.** Both phases add nodes and tools to the
  same registry; two owners means a merge conflict on the critical path.
- **At the end of this phase the play-screen frame and the trace row contract
  are frozen.** Phases 8, 9, 10 and 11 all touch the play screen, and each
  receives only its own additions. The freeze pins the **contract**, so those
  phases add renderers and entry points instead of renegotiating the pane — it
  assigns no **file ownership**, which README.md §3's group-C paragraph handles
  separately and is what actually prevents the collision.

**Surfaces extended.** Narration pane, composer, trace pane, failure /
refusal pattern.

---

## Phase 8 — Character creation in plain words

**Milestone.** A described character idea plus a follow-up question or two
becomes a finished character sheet with a portrait, and phase 4's pregen
becomes an explicit quick-start rather than a default.

**Capabilities landed.** The Character Generation Agent **and its prompt
asset**, `character_generation.md`; the Character Creation screen; Portrait
Media through OpenRouter's image generation, the media volume, the static route
and the deterministic placeholder; the settings promotion for the image model;
the state pane's portrait; the playthrough list's extension.

**What a reviewer sees working.**

- "Shy, strong, small, clever", plus a follow-up, becoming a coherent sheet
  with derived race, class and ability scores, and a portrait.
- **One** reject-and-re-derive before acceptance, and the sheet final after
  that. Regeneration is bounded so creation does not become a slot machine.
- An unusable description handled by asking again rather than by inventing.
- The quick-start path skipping creation entirely.
- A forced image failure **presenting as a portrait** — a silhouette or
  initial, with no error affordance and no retry button — and the sheet still
  acceptable. Portrait generation never blocks acceptance.

**Pays into.** Requirements 2 and 3, and the evidence for "can mention
differences between different agent types": this is a second, differently
shaped agent next to the turn loop. **Medium-3 is not claimed here** — see
[README.md](README.md) §5.

**Dependencies.** Phases 2, 4, 5 and 7 — unconditionally. **Ruled: the
clarifying dialogue reuses phase 7's interrupt machinery.** A second dialogue
mechanism would be a second way to do something the repo does one way, so this
is not left open and the dependency on 5 and 7 is not conditional on anything.
**Parallel with 9, 10 and 11** (group C), and one of the group's two
priorities.

**Open decisions owned.** Whether this capability is its own module or a
service inside `playthrough`; and what triggers the deterministic portrait
placeholder.

**Doc corrections owned.** **D7's second amendment** in
`roadmap/phase-0/shared-knowledge.md` — the image model becomes a declared
field. The register records that D7 is amended twice, in phase 2 and again
here, so the second amendment does not read as a contradiction of the first.

**Inherited constraints.**

- No portrait-only reroll.
- The portrait reuses the **existing OpenRouter credential**. No second
  provider and no new secret.
- Receives the **frozen** play-screen frame: it adds its own screen and the
  state pane's portrait, nothing else. The frame's entry points and the state
  pane are group-C shared files — see the seam ownership rule in
  [README.md](README.md) §3.
- **The image-failure evidence above uses phase 2's failure-injection seam.**
  This phase does not invent its own.
- **Generation and the portrait call write cost events.** They spend tokens
  outside the turn loop, and the run total is a sum over the event stream, so
  omitting them would make that total quietly false.
- **Conditional collision.** If this phase's placement decision resolves to a
  service inside `playthrough`, this phase and phase 9 both write into backend
  `playthrough` — generation here, the run-settings write surface there — and
  group C's independence no longer holds for that pair.

**Surfaces extended.** State pane, playthrough list. Character creation is
built once, here.

---

## Phase 9 — Developer drawer

**Milestone.** Model, temperature, personality id and one explicitly-marked
free-text system-prompt override are changeable per run, in a surface the
player experience does not contain. The drawer additionally displays the
composed effective prompt read-only and the pinned content version. A change
is carried into the run's next turn — observable in the composed prompt and in
the trace's model id and cost line, with the altered DM voice as the
demonstration rather than the acceptance criterion.

**Capabilities landed.** The Developer Drawer (frontend module `devtools`);
the run-settings write surface; the model and personality catalogues; the
read-only composed-prompt and content-version display.

**What a reviewer sees working.**

- The **composed effective prompt shown in the drawer containing the selected
  personality fragment**, and changing to the other fragment when the selection
  changes. Two personalities producing visibly different *narration* in the
  same scene is the **demonstration, not an acceptance criterion** — it is
  model-conditional and a QA agent cannot refute it.
- **A model swap reflected in the model id the trace carries** for the next
  turn, with the cost line moving accordingly. The cost figure is
  model-conditional; the recorded model id is not.
- The composed effective prompt updating as the override changes — this is the
  player-side-of-the-fence surface for phase 2's milestone.
- The player UI containing none of it.
- Settings replaying on resume, so a save reads back in the tone it was played
  at.
- The content version visible **only** here.

**Pays into.** **Medium-8's developer/player-split half.** The brief conjoins
the guard *and* the split, so phase 7 banks nothing on its own and **this phase
is not droppable**, notwithstanding that 8 and 10 are group C's priorities.
Also Easy-2, Easy-3 and Easy-4.

**Dependencies.** Phases 4 and 5 — buildable after 4, demonstrable only after
5, because temperature and personality have nothing to affect until a model
narrates. **Parallel with 8, 10 and 11** (group C).

**Open decisions owned.** **What the guard does about the free-text
system-prompt override.** The override sits in the system position, upstream of
everything a turn-inspecting guard looks at, so this decides whether Medium-8's
claim holds at the very phase meant to bank it. **The architect settles this in
this phase's step spec; the implementer does not.**

**Doc corrections owned.** None.

**Inherited constraints.**

- **The drawer carries no cost figures of its own.** Cost is player-facing and
  lives on the trace row and in the play-screen header; duplicating it behind
  the developer fence would give the same number two homes.
- **The first turn of every run uses the default settings**, because there is
  nowhere to choose a model before the run exists. Accepted consequence,
  stated rather than fixed — a pre-run settings step would put developer
  machinery in front of the player.
- Extends the **frozen** play-screen frame only by its entry point — a
  group-C shared file, so the seam ownership rule in [README.md](README.md) §3
  applies.
- **The free-text override carries a length cap**, like the player's turn input
  in phase 5. It is a system-position string reaching the model, so an uncapped
  field is a cost surface and an injection surface at once.

**Surfaces extended.** Play-screen frame. The drawer itself is built once,
here.

---

## Phase 10 — Agentic rule lookup

**Milestone.** The DM decides for itself when it needs a rule, may re-query,
and the player sees the SRD section it cited.

**Capabilities landed.** The `lookup_rule` tool; the citation trace renderer;
retrieval-failure handling.

**What a reviewer sees working.**

- A turn whose trace carries **a `lookup_rule` call with its query and its
  result count**, and the cited section alongside it. That is the refutable
  form; "the DM decided it needed a rule" is not observable, the recorded call
  is.
- A turn whose trace carries **no `lookup_rule` call**. Whether the DM
  *correctly* looks nothing up is the **demonstration, not an acceptance
  criterion** — the criterion is that a turn without a lookup exists and
  completes.
- **Two `lookup_rule` calls in one turn**, which is what a re-query looks like
  in the trace. Whether the second was prompted by a poor first result is
  model-conditional and demonstration only.
- A turn that proceeds gracefully when retrieval returns nothing.

**Pays into.** **Hard-1 banked.** Phase 3 built the corpus; this is where the
hard bonus actually ships. Also the vision's "the player never has to know the
rules": the agent looks them up.

**Dependencies.** Phases 3 and 5. **Parallel with 8, 9 and 11** (group C), and
one of the group's two priorities.

**Open decisions owned.** None.

**Doc corrections owned.** None.

**Inherited constraints.**

- Adds exactly **one trace renderer** against phase 5's pinned row contract.
- **Shares group C's seam with phase 11** — not only the tool registry but the
  **trace-renderer dispatch point**, which is one file both phases edit.
  Sequence the two, or give the seam a single owner; see
  [README.md](README.md) §3.
- Only the SRD is retrieved. Structured content is read from JSON, never
  through RAG.

**Surfaces extended.** Trace pane.

---

## Phase 11 — Journal memory

**Milestone.** The DM writes down what becomes true and recalls it later in
the campaign, including what the player invented; retrieval is visible, and a
read-only journal view is reachable from the play screen.

**Capabilities landed.** Journal Memory (backend module `journal`); the
`add_journal_entry` and `search_journal` tools; retrieval as top-k by
similarity **plus the most recent N unconditionally**, so the DM cannot forget
by choosing not to look; the journal view as a component inside frontend
`game`; the retrieval trace renderer. It calls the **embedding side of the LLM
Gateway** that phase 3 already added — there is no file to move and no
promotion to perform.

**What a reviewer sees working.**

- **A retrieval row in the trace, and recall after a reload.** The reload is
  the point: a same-session recall proves nothing a context window could not
  have done on its own.
- **The journal view containing the entry that records a nickname the player
  coined for an NPC.** The nickname later *surviving into the narration* is the
  **demonstration, not an acceptance criterion**: it is model-conditional,
  whereas the stored entry and its retrieval row are not.
- The journal view listing facts, not a transcript.

**Pays into.** **Medium-2, strengthened rather than banked.** `135.md` reads
"long-term **or** short-term", so phase 5's checkpointer already banks it; this
phase makes the memory claim substantially stronger and is the better
demonstration, but it is not what the bonus hangs on.

**Dependencies.** Phases 3 and 5. **Parallel with 8, 9 and 10** (group C).

**Open decisions owned.** The retrieval policy — top-k plus recency,
classification kept, weighted ranking dropped as unmeasurable against one
adventure of data.

**Doc corrections owned.** None.

**Inherited constraints.**

- **Shares group C's seam with phase 10** — the tool registry and the
  trace-renderer dispatch point both. See [README.md](README.md) §3.
- Journal entries are **facts, not prose**, and the journal is not a
  transcript. The event stream is what happened; the journal is what is true.
- A mis-retrieved entry can contradict established canon, because situational
  facts have no deterministic flag store. This is a recorded, accepted gap, not
  a defect to fix here.
- Adds the journal entry point to the **frozen** play-screen frame, plus one
  trace renderer — both group-C shared files, so the seam ownership rule in
  [README.md](README.md) §3 applies.
- **The journal view is a component inside frontend `game`**, not a frontend
  module of its own: it is one read-only pane plus one hook, rendered by
  `game`'s play screen. Backend `journal` *is* a module, because it has its own
  table and its own lifecycle. The two are not the same case.
- **Stored injection is this phase's own security surface, and no earlier
  phase covers it.** Journal entries are partly derived from player text and
  are **re-injected into later prompts**, so phase 7's guard — which inspects a
  turn's input — does not reach them. This phase owns whatever mitigation it
  chooses, and must say what that is rather than inherit a guard that does not
  apply.
- **The revision chain is linear.** This phase adds a table while group C runs,
  repeating group B's revision-head hazard, and takes its place in the same
  explicit revision order.

**Surfaces extended.** Play-screen frame, trace pane. The journal view is
built once, here, as a component of frontend `game`.

---

## Phase 12 — Release: observability & documentation

**Milestone.** Every **chat-model** call is traceable in Langfuse when tracing
is enabled, and the documentation lets a stranger run and understand the agent,
with worked examples and the reasoning behind the technical decisions.

**Capabilities landed.** The Langfuse callback wiring on the gateway; the
module docs completed and `docs/README.md`'s index brought up to date; the
tool reference; the content authoring guide; usage and worked examples; the
`requirement-map.md` correction; the remaining `general/` corrections.

**What a reviewer sees working.**

- A played turn appearing as a trace tree in Langfuse — **its chat-model calls,
  and only those.** Embedding calls are absent by nature, not by omission:
  LangChain's embeddings class emits no callback events, as `.env.dist` already
  states, so phase 3's ingestion and phase 11's journal writes are outside the
  trace and the milestone does not claim otherwise.
- **A fresh-checkout run-through reaching a named end state**, following the
  documentation alone. Not "the docs exist" — the docs work, and the end state
  is named so the claim is refutable.

**Pays into.** **Requirement 5**, which is graded. **Hard-2 as insurance**
alongside Hard-1.

**Dependencies.** Split, deliberately: the **Langfuse half needs phase 2**;
the **documentation half needs phase 11 and whatever of group C lands**,
because it cannot document character creation, the drawer or the rule tool
before they exist. Recording it as "depends on everything" would hide
schedulable work.

**Open decisions owned.** None.

**Doc corrections owned.** `general/requirement-map.md`'s optional-task table —
the corrected bonus slate; **Langfuse counted as insurance and scoped to
chat-model calls only**; **Medium-2 banked by the checkpointer alone**, with the
journal strengthening it; **Medium-8 requiring both halves**, so neither phase 7
nor phase 9 banks it alone; and **Medium-3 recorded as considered and not
claimed, with the reasoning**, because a reviewer who sees the judgement scores
it better than one who sees an overreach. Also the full argument for
[README.md](README.md) §7's requirement-3 reading. And
`general/architecture.md`'s "Current state: scaffolding … the game agent does
not [exist]", which by this phase is no longer true.

**Inherited constraints.** Module documentation is a **per-phase obligation**,
so this phase completes and cross-checks the set rather than authoring it from
scratch. If it finds itself writing eleven module docs, an earlier phase
skipped its own.
