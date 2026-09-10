---
title: "Stage-01 — phases"
stage: 1
created: 2026-09-10
---

# Stage-01 — phases

One section per phase, eleven in all, in implementation order. The stage-level
contract — capability inventory, classification, dependency graph, scope fence,
the ordering verdict, the registers — is [README.md](README.md); this file is
the per-phase detail.

Each section states the phase's **Milestone** as shipped functionality, the
capabilities it lands, **what a reviewer can see working**, what it pays into,
its dependencies and parallelism, the open decisions and doc corrections it
owns, and the constraints it carries. **No steps, no routes, no columns, no
payload shapes** — those are the step specs' business, and the phase
directories that hold them arrive with each phase.

"Sees working" is evidence a reviewer can produce themselves. **For seven of
the eleven phases that evidence is a command or a wire-level exchange, not a
screen** — the order is the dependency graph's, not a demo script's. Each such
phase names the demonstrable that *is* its milestone and the later phase that
surfaces it; the argument is [README.md](README.md) §7.

---

## Phase 1 — Content schema and the authored set

**Milestone.** A content schema exists, and one campaign, one adventure, at
least three scenes, its definitions, an authored prose `intro` per adventure
and a seed player character are authored against it. The set loads at a pinned
content version, and a validation command locates any referential error.

**Capabilities landed.** Content Schema & Loader (backend module `content`);
the Authored Content Set, including the per-adventure `intro` and the seed
player character; the Content Validation CLI.

**What a reviewer sees working.**

- The validation command passing on the shipped set.
- A deliberately broken exit reference or an unknown definition id producing a
  **precise, located** error — content integrity is loader-enforced, so this is
  the only place a typo is ever caught.
- A scene, an adventure's `intro`, and the seed player character, each printed
  by id at a pinned version.
- The campaign present and readable in the content read surface.

**Pays into.** Requirement 2 (the content layer) and "a relevant knowledge base
for their domain". This is also where [README.md](README.md) §7's
player-capability reading of requirement 3 is first stated.

**Dependencies.** Phase 0 only. Content is hand-authored, so no model is
needed. **Parallel with 2 and 3** (group A) — sharing one file, `app/cli.py`,
where this phase registers its validation command; see
[README.md](README.md) §3 for the ordering rule that covers it.

**Open decisions owned.** None.

**Doc corrections owned.** `general/model.md`'s content shape, which describes
neither the per-adventure `intro` nor the seed player character;
`general/architecture.md`'s "authored by an LLM once through a
`generate_adventure` CLI" sentence; `general/requirement-map.md`'s
requirement-3 wording; and the first `docs/modules/` entry with its
`docs/README.md` row.

**Inherited constraints.**

- **One phase, with the schema fixed before any content is authored.** That
  ordering is step order, which is what steps are for. **The split into a
  schema phase and an authoring phase was considered and rejected**: a schema no
  content has ever been written against is **not falsifiable** — "this schema
  expresses what an adventure needs" cannot be refuted without an adventure —
  and shipping one would park a half-capability for a later phase.
- **Authoring feedback amends the schema within this phase.** The second scene
  teaches you the schema is missing a field; if the schema were a completed
  prior phase, every such discovery would reopen it.
- The milestone claims only that the content is **present and readable**, which
  is what the evidence above proves. It deliberately avoids "startable" and
  "playable": starting is phase 7's verb and playing is phase 8's.
- **The seed player character is content, not scaffolding**, and it is **not a
  quick-start**. It exists so phase 5 has a character before the generation
  agent lands, and it stays as a test fixture. §4 fences out any player-facing
  path that skips creation.
- **No screen.** Surfaced by **phase 7** (the run the content is pinned to) and
  **phase 8** (the scenes the DM reads).

---

## Phase 2 — The OpenRouter seam and prompt assets

**Milestone.** One seam carries chat, embedding and image calls on one
credential with one failure classification. Each kind round-trips, and each
fails cleanly and distinguishably. A prompt asset resolves by id against the
root convention. The LangGraph checkpointer's schema is provisioned and
excluded from Alembic.

**Capabilities landed.** The OpenRouter seam (`core/` singleton) covering all
three call kinds; prompt-asset resolution **and the root convention it resolves
against**; checkpointer provisioning and the Alembic exclusion of its schema;
the settings promotion for the credential, the three model ids and the
embedding dimension; the LangChain, LangGraph and checkpointer dependency
additions.

**Two conventions were considered for this phase and deliberately moved out.**
The **graph-thread convention** cannot be pinned here — no run exists yet for a
thread id to derive from — so **phase 7 pins it**, where a pending question
surviving a reload proves it. The **tool-error convention** gets no executable
proof until bindings land on it, so **phase 8 writes it**. Both were dropped
rather than carried, because a capability with no producible evidence in the
phase that ships it fails this stage's own falsifiability rule — and the
tool-error convention is the one real residual of the mechanics-first verdict,
which is better stated than hidden.

**What a reviewer sees working.**

- One chat call round-tripping with its token and cost figures, one embedding
  call returning a vector of the pinned width, and one image call returning
  bytes.
- A bad key, an unreachable base URL and a request timeout each failing
  **distinguishably** — one is a configuration fault, one a connectivity fault,
  one a runtime fault, and conflating them is the phase-0 `unwrap()` mistake
  repeated on the backend.
- A prompt asset resolving by id **against a fixture asset**, and an unknown id
  failing specifically. The resolver is what this phase ships; the shipped
  prompts land with their agents in phases 7 and 8, because an id resolves
  against its owning capability's own prompt directory.
- `alembic upgrade head` → `downgrade base` → `upgrade head` round-tripping
  against a fresh database with the checkpointer's schema present and
  untouched — a stray autogenerate must not try to drop it.

**Pays into.** Requirements 2 and 4; groundwork for Easy-2, Easy-3 and Easy-4,
which phase 10 banks.

**Dependencies.** Phase 0 only. **Parallel with 1 and 3** (group A).

**Open decisions owned.**

- Where the cost figure comes from — a static price table in settings, or
  OpenRouter's usage-accounting field. Decided here because phase 9 renders it
  and a wrong number is worse than no number. **Trap to know before speccing:
  the static-table branch needs new declared settings that `.env.dist` has no
  entries for, and `.env.dist` is owner-only.**
- **The failure-injection seam**: how a provider failure is produced on demand
  — an unreachable base URL, a bogus model id, an injected timeout. A bad key
  is producible by editing `.env`, but **phase 8's timeout evidence and phase
  7's image-failure evidence are not**. This phase defines one seam and both
  reuse it, rather than each inventing its own.
- Whether LangChain's OpenAI-compatible embeddings class can be pointed at the
  OpenRouter base URL, and so whether the seam's embedding side is a
  configuration of that class or a thin call of its own. **Use `mcp__context7`
  when this phase is specced; do not answer it from recall.**

**Doc corrections owned.** `general/model.md`'s static-file tree, which must
not list a content-generation prompt asset **and must not pin `game`'s
directory as the only prompt root** — doing so would place phase 7's
character-generation prompt inside `game` even if the character capability
becomes its own module, which is a module-boundary violation. The correction is
the root convention itself: an id resolves against its owning capability's own
prompt directory. Also `general/backend-stack.md`'s claim
that LangChain and LangGraph are already declared; and **D7's single
amendment** in `roadmap/phase-0/shared-knowledge.md` — the credential, the
three model ids and the embedding dimension all become declared fields
together, because all three call kinds land on one seam in one phase.

**Inherited constraints.**

- **This phase lands no module.** Everything in it is `core/` infrastructure by
  nature, so there is no module for a single-caller version to live in and
  promotion on evidence does not apply. It also lands **no prompt asset** — only
  the convention and the resolver.
- **Group A shares `app/cli.py`**, where this phase registers its two
  round-trip commands; see [README.md](README.md) §3.
- **There is no agent base class, and none is to be created.** Two LangGraph
  graphs with different node sets, different tool sets and different
  termination conditions share a *library*, not a base — agents are created
  when needed. What this phase ships is the shared plumbing that has evidence
  here: the seam, prompt-asset resolution with its root convention, and the
  checkpointer. The two shared *conventions* move to their first consumers, as
  above. **Prompt composition is shared by nothing** — the character agent has
  one prompt file and nothing to compose, so the composer has one caller and
  lands in phase 8.
- **No screen.** Surfaced by **phase 8** (the prompt drives the narration) and
  **phase 10** (the drawer shows the composed prompt read-only).

---

## Phase 3 — Dice and mechanics

**Milestone.** Dice expressions parse and resolve deterministically with a
visibility flag, and an invalid expression is rejected specifically. No model,
no database.

**Capabilities landed.** Dice & Mechanics as a module of pure functions inside
`game` — **which this phase therefore creates and phase 8 completes**.

**What a reviewer sees working.**

- A command rolling an expression and reporting the individual dice, the
  modifier and the total, reproducibly under a fixed seed.
- A roll carrying a visibility flag, so the distinction the player view later
  depends on exists at the bottom of the stack rather than being added on top.
- An invalid expression rejected with a specific, named error rather than a
  zero or an exception.
- The test suite, which is the substance of this milestone: determinism is a
  property nothing but tests can establish.

**Pays into.** Requirement 4, and the vision's "the dice are real" principle —
outcomes come from actual rolls against actual target numbers, so the thing
producing them must be provably deterministic before anything narrates over it.

**Dependencies.** Phase 0 only — this capability depends on nothing at all.
**Parallel with 1 and 2** (group A) — sharing one file, `app/cli.py`, where
this phase registers its roll command; see [README.md](README.md) §3.

**Open decisions owned.** None.

**Doc corrections owned.** None.

**Inherited constraints.**

- **Dice live with their only caller from the start.** The `roll_dice` binding
  in phase 8 is the sole consumer, forever, so promotion on evidence puts dice
  inside `game`; this phase creates that module holding only dice. Placing them
  in `core/` would be speculative, and a module of their own would be one that
  later gets folded.
- **This is the smallest phase in the stage**, and deliberately so: it is the
  one artefact that must be provably deterministic, and reviewing it beside an
  agent is where that proof gets lost.
- **No screen.** Surfaced by **phase 8** (real rolls in real turns) and
  **phase 9** (the roll rows the player reads).

---

## Phase 4 — SRD knowledge base

**Milestone.** SRD 5.1 is ingested into pgvector, and a rules query returns
relevant passages with citable section references.

**Capabilities landed.** pgvector enablement; the SRD Rule Ingestion CLI; the
Rule Lookup service. **No tool binding** — that arrives in phase 8 with the
registry that receives it.

**What a reviewer sees working.**

- An ingest run reporting its counts.
- A query command answering a real rules question with its cited sections.
- A re-ingest replacing the corpus wholesale — an SRD rule is owned by nobody
  and is rebuilt, never migrated.
- A query against an empty corpus failing cleanly, rather than returning
  nothing indistinguishable from a miss.

**Pays into.** **Hard-1's corpus half.** Phase 8 banks the agentic half, and
phase 9 makes the citation visible.

**Dependencies.** Phase 2 (the seam's embedding side). **Parallel with 5**
(group B).

**Open decisions owned.**

- **How the migration expresses the vector width — and only that.** `.env.dist`
  already pins the embedding model, states its native size, states that no
  `dimensions` parameter is ever sent, and requires a migration to change it.
  Nothing about the model is open here, and **this phase must not pick a
  different one: `.env.dist` is owner-only.**
- **How** a fixture-local real engine is driven — not whether one is allowed,
  which `backend-stack.md` already permits. Doing it against async SQLAlchemy
  collides with the landed "fully synchronous suite, no `pytest-asyncio`, no
  async fixtures" rule, so this phase may have to **amend a landed decision**
  rather than merely make one. Similarity search is inherently database-bound,
  so it cannot be deferred, and `qa-backend` needs the policy pinned rather
  than improvised. **Phase 5 inherits the answer.**

**Doc corrections owned.** Conditional on the decision above: if a
fixture-local async engine is needed, the "fully synchronous suite" rule in
`general/backend-stack.md` and phase 0's shared knowledge is amended here, not
worked around.

**Inherited constraints.**

- **Only the SRD is retrieved.** Structured content is read from JSON, never
  through RAG.
- **The revision chain is linear.** This phase and phase 5 run in parallel and
  would otherwise stack revisions on the same `down_revision` while both adding
  a line to `alembic/env.py`. The two are assigned an explicit revision order
  and the later rebases onto the earlier one's head.
- **No screen.** Surfaced by **phase 9** (the cited section the player reads).

---

## Phase 5 — Runs, object state and the event stream

**Milestone.** A run exists: it pins its content version, owns validated
objects with a validated write path — including the character's scene placement
and its advance on an exit — owns an append-only visibility-filtered event
stream whose cost is a sum, and is listable, archivable and resumable.

**Capabilities landed.** Runs (backend module `playthrough`) with the per-run
settings store; the object state models, their read surface and their validated
write path; scene placement and advance; the Event Stream and Cost Accounting
(backend module `events`); instantiation of phase 1's seed player character.

**What a reviewer sees working.**

- A run started against the shipped campaign, listed, opened, archived,
  unarchived and resumed — at wire level, since this phase ships no screen.
- Several concurrent runs coexisting.
- The seed character present with its validated state, and an **invalid state
  write rejected**. Without this, the "deterministic mechanics" layer is
  decoration.
- The character **moving to another scene on an exit**, and an invalid exit
  refused.
- Events appended and read back in order, with a **DM-visibility event present
  in the store and absent from the player-filtered read**.
- A cost total that is a **sum over the stream**, reading zero because nothing
  has spent anything yet.
- A second user unable to reach the first user's run — authorisation is
  ownership, and this is the first phase where there is anything to own.

**Pays into.** Requirement 4 (rejected writes); Medium-4's personalisation half
on top of the landed authentication; and Medium-1's foundation, whose figures
arrive in phase 7 and whose display arrives in phase 9.

**Dependencies.** Phase 1 (the content loader, for the pin and the eager
instantiation). **Parallel with 4** (group B).

**Open decisions owned.** Ownership of a run — a membership row or a user id;
the adventure's progress — its own entity or fields on the run; and whether the
object state models and their read surface are their own module or a service
inside `playthrough`. The roadmap deliberately pins none of the three.

**Doc corrections owned.** Every combat-removal correction:
`general/model.md`'s combat paragraph, the encounter node in the entity
diagram, "Encounter hangs off AdventureRun" and the encounter line in the
lifecycle table; `general/glossary.md`'s **Encounter** entry and its
**Initiative** game term, which now has no caller;
`general/app-vision.md`'s "turn order beside the narration"; and
`general/architecture.md`'s "state panel (HP, AC, inventory, turn order)".

The rest of `general/model.md`'s lifecycle table comes with it, since this
phase owns that table. The **Purge** row describes a capability Stage-01 fences
out. The "generate the player's creature" row is **a confirmation, not a
correction**: it is correct as written, because phase 7 does exactly that —
which is *why* character creation and the run are adjacent rather than
swapped. Only the **seed character's fixture role** needs stating, and
`general/glossary.md` needs a term for it, since nothing currently names the
thing this phase instantiates before the generation agent exists.

**And two conditional corrections that must be resolved either way.**
`general/model.md` writes "ownership lives on the membership row" as a *ruling*
and `general/architecture.md` repeats it; `general/model.md` writes the
adventure's progress as a full entity with its own justification. This roadmap
records both as **open decisions**. If this phase overturns either, it corrects
those files; if it upholds either, it records that the decision is closed. **A
phase-5 architect must not be left reading two documents that disagree about
whether there is a choice.**

**Inherited constraints.**

- **This phase is headless by design, and no run it creates is startable by a
  player.** That is the arrangement, not a gap: the player-facing way to begin
  a run only ever ships alongside character creation in phase 7, which is what
  makes "no character, no game" true by construction. The rejected alternative
  — generating a character before any run exists — buys an orphan storage
  location and a migration out of it, for nothing.
- **Scene placement and advance land together.** An earlier draft split them,
  holding the advance back on the grounds that position is object state and a
  write needs a validated write path. **That split is resolved rather than
  deferred**: the validated write path is in *this* phase, so there is no
  writer-without-a-path to avoid.
- **The revision chain is linear** — see phase 4; and phases 6 and 7 both
  alter this phase's tables, so they take their place in the same order.
- **No screen.** Surfaced by **phase 7**.

---

## Phase 6 — Journal memory

**Milestone.** Facts are written, embedded, and retrieved by similarity **plus
the most recent N unconditionally**, so nothing depends on the retriever
choosing to look.

**Capabilities landed.** Journal Memory (backend module `journal`): the write
path with embedding on write, and the retrieval path. **No tool binding** —
that arrives in phase 8.

**What a reviewer sees working.**

- Facts written and listed back, as **facts rather than a transcript** — the
  event stream is what happened, the journal is what is true.
- A retrieval returning a semantically related entry that shares no keyword
  with the query, which is the only way to show the embedding is doing work.
- A retrieval returning **the most recent entries even when they are poor
  similarity matches**, which is the property the unconditional-recency half
  exists for.
- Entries cascading away with the run that owns them.

**Pays into.** **Medium-2, strengthened rather than banked.** `135.md` reads
"long-term **or** short-term", so phase 7's checkpointer banks it; this phase
makes the memory claim substantially stronger and is the better demonstration,
but it is not what the bonus hangs on.

**Dependencies.** Phase 2 (the seam's embedding side) and phase 5 (the run that
owns the entries). **Parallel with 7** (group C).

**Open decisions owned.** The retrieval policy — top-k plus the most recent N
unconditionally, classification kept, **weighted ranking dropped** as
unmeasurable against one adventure of data.

**Doc corrections owned.** None.

**Inherited constraints.**

- **Stored injection is this phase's own security surface, and no other phase
  covers it.** Journal entries are partly derived from player text and are
  **re-injected into later prompts**, so phase 8's guard — which inspects a
  turn's input — does not reach them. This phase owns whatever mitigation it
  chooses and must say what it is, rather than inherit a guard that does not
  apply.
- A mis-retrieved entry can contradict established canon, because situational
  facts have no deterministic flag store. A recorded, accepted gap, not a
  defect to fix here.
- **The revision chain is linear** — this phase adds a table and takes its
  place in the order established in group B.
- **No screen.** Surfaced by **phase 9** (the journal view and the retrieval
  row in the trace).

---

## Phase 7 — Character creation, and how a run begins

**Milestone.** A player signs in, describes a character in plain words, answers
a follow-up question or two, receives a finished character sheet with a
portrait, and lands in a run that is listed, archivable and resumable.

**Capabilities landed.** The Character Generation Agent and its prompt asset,
**which lives with the capability, not under `game`**, per phase 2's root
convention; **the interrupt convention** and **the graph-thread convention**,
both pinned here as their first consumer; Portrait Media through OpenRouter's
image generation, with the media volume, the static route and the deterministic
placeholder; the App Shell
promotion; the Playthrough Browser; the Character Creation screen; the
character sheet / state display; the term-explanation pattern; the failure
pattern.

**What a reviewer sees working.**

- "Shy, strong, small, clever", plus a follow-up, becoming a coherent sheet
  with derived race, class and ability scores, and a portrait.
- **One** reject-and-re-derive before acceptance, and the sheet final after
  that — regeneration is bounded so creation does not become a slot machine.
- An unusable description handled by asking again rather than by inventing.
- **A pending question surviving a reload**, which proves two conventions at
  once on a two-question dialogue rather than inside a nine-tool loop: the
  interrupt's wire shape and resume rule, and the **graph-thread convention** —
  a thread derived from the run, resolving across a process boundary.
- A forced image failure **presenting as a portrait** — a silhouette or
  initial, with no error affordance and no retry button — and the sheet still
  acceptable.
- The finished run appearing in the browser's list, and the archive filter and
  unarchive-with-confirm working from there.
- **No way to reach a run without creating a character.**

**Pays into.** Requirements 2 and 3 — this is the stage's **first
player-visible milestone**. **Medium-2 banked**: the character agent is the
checkpointer's first consumer, and the brief reads "long-term *or*
short-term". Also the evidence for "can mention differences between different
agent types", since this is a differently shaped agent from the turn loop.
**Medium-3 is not claimed** — see [README.md](README.md) §5.

**Dependencies.** Phase 2 (the seam's chat and image sides, prompt-asset
resolution, the checkpointer) and phase 5 (somewhere to write the sheet).
**Parallel with 6** (group C).

**Open decisions owned.** Whether this capability is its own module or a
service inside `playthrough`; what triggers the deterministic portrait
placeholder; and the exact wording of the i18n carve-out — **agent-authored
content is verbatim model output and is exempt from the i18n-key rule** —
owned here because the character sheet is the first model output rendered.

**Doc corrections owned.** `general/frontend-stack.md`'s i18n section, which
currently says every user-facing string goes through a key with no carve-out
for verbatim model output.

**Inherited constraints.**

- **Character generation does not stream.** Its dialogue is short and
  turn-taking, so request/response is enough; SSE lands in phase 8 with
  narration, the only thing long enough to need it. A second streaming consumer
  would buy latency cover nobody feels.
- **The interrupt and graph-thread conventions pinned here are reused verbatim
  by phase 8.** Both are conventions — a wire shape, a resume rule, a thread
  derivation — not promoted files, so nothing moves later. The DM loop is their
  second consumer, not their author. Phase 2 was considered as the home for the
  thread convention and rejected: no run exists there for a thread id to derive
  from, so it would have been unprovable where it was written.
- **Generation and the portrait call write cost events.** This phase is the
  **first writer to the event stream**, and the run total is a sum over it, so
  omitting them would make phase 9's total quietly false.
- **The app-shell promotion is conditional.** The shell graduates from
  `modules/home` to `src/components/` only if it keeps its
  `action?: ReactNode` slot pattern and **imports from no module**, per D1's
  worked example. This phase adds navigation, which is exactly where sign-out
  and current-user creep in; if they do, the shell has not earned the promotion
  and stays where it is.
- **No portrait-only reroll**, and portrait generation **never blocks
  acceptance** of the sheet.
- The portrait reuses the **existing OpenRouter credential**. No second
  provider and no new secret.
- **The image-failure evidence above uses phase 2's failure-injection seam.**
  This phase does not invent its own.
- **The revision chain is linear** — this phase alters phase 5's tables and
  takes its place in the order.

**Surfaces created here, and where they go next.** App shell → 9, 10.
Playthrough browser → 9. Character creation screen → built once. Character
sheet / state display → 9. Term-explanation pattern and failure pattern → 9,
where each is **promoted to `src/components/` unchanged** on its second
caller.

---

## Phase 8 — The DM turn

**Milestone.** A turn runs end to end over the wire. Plain words in, streamed
narration out with agent-progress milestones; the DM reads scene facts and
stat blocks, rolls real visibility-aware dice, writes validated state and
advances scenes, cites SRD sections, writes and recalls journal facts,
interrupts when the decision is the player's, and refuses prompt injection and
out-of-band state claims. Every turn is recorded with its cost, and a failed
turn is recoverable without eating the input.

**Capabilities landed.** The Dungeon Master Agent — the LangGraph loop over the
checkpointer — and **its whole tool registry at once**: `get_scene`,
`get_monster`, `roll_dice`, `update_object`, `lookup_rule`,
`add_journal_entry`, `search_journal`, `ask_player`. Plus the DM's system
prompt and personality fragments, which live with `game` per phase 2's root
convention; the Prompt Composer; the Guard; the Turn Transport over SSE;
per-turn event and cost writing; Turn Failure & Recovery; the turn-input length
cap; and **the tool-error convention**, written here because this is where
bindings first land on it and therefore the first place it has producible
evidence.

**What a reviewer sees working.**

At wire level — a scripted client, not a browser:

- A real turn, streamed, with progress milestones arriving while it is in
  flight.
- A check resolved with a visible roll against a target number, and the
  character's state changed as a consequence.
- A roll **recorded with DM visibility, with nothing in the stream referring to
  it** — no milestone, no row, no hint. The narration *reflecting* that hidden
  outcome is the **demonstration, not an acceptance criterion**: the flag and
  the absent stream tell are observable, the model's use of the result is not.
- A turn carrying a `lookup_rule` call with its query and result count, and the
  cited section alongside it; and another turn carrying no such call.
- A turn's trace recording **every** `lookup_rule` call individually with its
  own query, so two calls are distinguishable from one — which is what makes a
  re-query representable. The DM *choosing* to re-query after a poor first
  result is the **demonstration, not an acceptance criterion**; a re-query
  cannot be forced.
- A journal fact written during one turn, and a **`search_journal` call in a
  later turn after a process restart returning that entry**. The narration then
  *using* the recalled fact is the **demonstration, not an acceptance
  criterion**: the retrieval call and its result are observable, the model's use
  of them is not.
- A turn that stops on a decision and presents its options, and a reload that
  returns to the same pending decision.
- "My HP is 100" refused with an explanation and **no state change** — now a
  meaningful assertion, because the validated write path landed in phase 5.
- A prompt-injection attempt refused, and the refusal recorded.
- Every turn's cost recorded, and the run total still a sum.
- A forced provider timeout terminating the stream with the error object,
  preserving the input and leaving the turn retryable; and a **completed** turn
  that is not retryable.

**Pays into.** Requirements 2, 3 and 4. **Medium-8's guard half** — phase 10
banks the other half and neither banks it alone. **Hard-1's agentic half** —
the corpus was phase 4; this is where the DM decides for itself. Medium-1's
real figures.

**Dependencies.** Phases 1, 2, 3, 4, 5, 6 and 7. **Parallel with nothing** —
this is the integration phase, and everything before it exists to make it
smaller.

**Open decisions owned.**

- **The agent-progress milestone vocabulary**, bound by the constraint that
  **nothing in the stream may reveal that a hidden roll happened**. A
  "rolling…" milestone during a hidden check is exactly the tell the vision
  forbids. Now a single phase's own decision rather than a cross-phase
  constraint, because the stream and the rolls land together.
- **The in-stream error representation.** *Ruled: one error shape, two
  transports* — a turn failing after the 200 terminates the stream with an
  event carrying the same `{code, message, details}` object, so D4's single
  shape holds even though the transport differs. This phase pins the remaining
  transport detail.

**Doc corrections owned.** `general/architecture.md`'s tool table, losing its
`start_combat()` / `end_round()` rows; `general/architecture.md`'s wire
convention, which gains SSE as a third response kind — **and must state
affirmatively that D5 is not amended**, because a long-lived SSE response is
still one request, so "request-scoped or a CLI one-off" still holds and nobody
should read the streaming ruling as breaking it; and
`general/requirement-map.md`'s "`ask_player` **every turn**", which contradicts
this milestone.

**Inherited constraints.**

- **This is the largest milestone in the stage**, and it is one seam: the loop,
  the guard, the prompts, the transport and the whole registry are not
  separable without shipping a half-capability. The only dependency-correct
  relief taken is splitting the frontend off as phase 9 along the wire
  contract. The reasoning, and the earlier split this reverses, are in
  [README.md](README.md) §3.
- **There is no dumb-agent stage.** Every service the registry binds — dice,
  the validated write path, rule lookup, journal read and write — landed as a
  finished, tested capability in phases 3 to 6. A binding is a thin adapter to
  a service that already works.
- **The guard ships in the same phase as the loop it guards.** There is no
  window in which a free-text-into-tool-calling surface exists unguarded.
- **The guard's override hook is left here; phase 10 decides what passes
  through it.** The free-text system-prompt override arrives in phase 10, in
  the system position, upstream of everything a turn-inspecting guard reads —
  so this phase owns the seam and phase 10 owns the policy.
- **The interrupt and graph-thread conventions are phase 7's, reused
  verbatim.** The `ask_player` binding does not re-invent a wire shape, and the
  loop does not re-invent a thread derivation.
- **The tool-error convention is written here, not inherited.** It was
  considered for phase 2 and moved, because it has no executable proof until
  bindings land on it — which happens here, on eight at once. That
  simultaneity is the one real residual of the mechanics-first verdict, and
  this phase owns it rather than discovering it.
- **The turn's free-text input carries a length cap**, enforced server side: an
  uncapped field is a cost surface and a prompt-injection surface at once.
- **Prompt scope.** With combat out of Stage-01, a fight resolves in one or two
  rolls and their consequences, never as simulated rounds — a model given dice
  and monsters will otherwise invent an initiative order the system cannot
  track. The prompt also instructs plain language and requires the DM to
  self-explain any game term it uses, which is the mitigation for the i18n
  carve-out leaving narration prose unannotated.
- **No turn cancel.** Retry exists for a failed turn only.
- **No screen.** Surfaced by **phase 9**, immediately.

---

## Phase 9 — The play screen

**Milestone.** The player plays in a browser: narration, live character state,
a filtered trace carrying the visible rolls, the cited sections, the
retrievals, the refusals and the per-turn and run cost, decision prompts when
the DM asks, retry on a failed turn, and no roll row for a hidden roll.

**Capabilities landed.** The play-screen frame; the narration pane; the
composer; **the trace pane and every one of its renderers, written once**; live
updates to **phase 7's state display**, imported as a named cross-module
surface rather than rebuilt — there is no second state pane in `game`; the
journal view as a component of frontend `game`; the decision-prompt affordance;
the retry affordance; the promotion of the term-explanation and failure
patterns to `src/components/`.

**What a reviewer sees working.**

- A turn played in the browser, narration streaming in, with progress
  milestones while it works.
- Phase 7's state display, now live: hit points changing as a consequence, and
  the character moving between scenes.
- Trace rows for the visible roll (expression, result, target), the cited
  section, the retrieval, the refusal and the interrupt — **each collapsed to a
  one-line summary**, with per-turn cost on the row and the run total in the
  header and on the list row.
- **A hidden-roll turn whose narration reflects a real outcome with no roll
  row.** That is the browser-visible half; the payload-level assertion that a
  hidden roll never reaches the client stays a QA criterion, because a reviewer
  cannot see the absence of a field.
- The journal view listing facts, **including the entry that records a nickname
  the player coined for an NPC**. The nickname later surfacing in the narration
  is the **demonstration, not an acceptance criterion**: it is
  model-conditional, whereas the stored entry and its retrieval row are not.
- A decision prompt answered, and a reload returning to a pending one.
- A failed turn offering retry with the input preserved, and a completed turn
  offering none.
- **A small-screen arrangement in which state and trace are demoted beneath
  the narration and closed by default**, and a wide one in which the trace is
  open with its rows collapsed. The breakpoint and the exact arrangement belong
  to the UI spec, not to this roadmap.

**Pays into.** **Medium-1 banked** — this is where cost becomes visible.
**Hard-1's citation made visible.** Requirements 2, 3 and 4.

**Dependencies.** Phase 8 (the wire contract). **Parallel with nothing.**

**Open decisions owned.** None.

**Doc corrections owned.** None.

**Inherited constraints.**

- **Every trace renderer is written here, once.** An earlier draft had the
  renderers arrive across four later phases, which forced the play-screen frame
  and the trace row contract to be frozen mid-stage and a shared file seam
  assigned a single owner. **None of that survives the reorder**: renderers
  arrive with the events they render, so nothing edits a dispatch point twice
  and there is no freeze to enforce.
- **Cost is player-facing.** It belongs on the trace row and in the header, not
  behind the developer fence.
- **The content version is invisible to the player.** It appears read-only in
  the drawer (phase 10) and nowhere in player chrome.
- **The journal view is a component, not a module**: one read-only pane plus one
  hook, rendered by the play screen. Backend `journal` *is* a module, because it
  has its own table and its own lifecycle. The two are not the same case.
- **Agent-authored content is rendered verbatim** — narration, citations,
  option labels and journal facts carry no i18n key, per the carve-out phase 7
  pinned. Every other string does.

**Surfaces created here, and where they go next.** Play-screen frame,
narration pane and composer → 10, by its entry point only. Trace pane and every
renderer → built once. Journal view → built once. **The state display is
extended here, not created** — phase 7 owns it.

---

## Phase 10 — Developer drawer

**Milestone.** Model, temperature, personality id and one explicitly-marked
free-text system-prompt override are changeable per run, in a surface the
player experience does not contain. The drawer additionally shows the composed
effective prompt and the pinned content version, read-only.

**Capabilities landed.** The Developer Drawer (frontend module `devtools`); the
run-settings write surface; the model and personality catalogues; the read-only
composed-prompt and content-version display.

**What a reviewer sees working.**

- **The composed effective prompt shown in the drawer containing the selected
  personality fragment**, and changing to the other fragment when the selection
  changes. Two personalities producing visibly different *narration* in the same
  scene is the **demonstration, not an acceptance criterion** — it is
  model-conditional and a QA agent cannot refute it.
- **A model swap reflected in the model id the trace carries** for the next
  turn, with the cost line moving accordingly. The cost figure is
  model-conditional; the recorded model id is not.
- The player UI containing none of it.
- Settings replaying on resume, so a save reads back in the tone it was played
  at.
- The pinned content version visible **only** here.

**Pays into.** **Medium-8's developer/player-split half.** The brief conjoins
the guard *and* the split, so phase 8 banks nothing on its own and **this phase
is not droppable.** Also Easy-2, Easy-3 and Easy-4.

**Dependencies.** Phase 5 (the run-settings store), phase 8 (the composer, and
something for the settings to affect) and phase 9 (a frame to hang the entry
point on).

**Open decisions owned.** **What passes through the guard's override hook.** The
override sits in the system position, upstream of everything a turn-inspecting
guard reads, so this decides whether Medium-8's claim holds at the phase meant
to bank it. Phase 8 left the hook; **this phase owns the policy, and the
architect settles it in this phase's step spec — not the implementer.**

**Doc corrections owned.** None.

**Inherited constraints.**

- **The drawer carries no cost figures of its own.** Cost is player-facing and
  lives on the trace row and in the play-screen header; duplicating it behind
  the developer fence would give the same number two homes.
- **The free-text override carries a length cap**, like the turn input in phase
  8. It is a system-position string reaching the model, so an uncapped field is
  a cost surface and an injection surface at once.
- **The first turn of every run uses the default settings**, because there is
  nowhere to choose a model before the run exists. An accepted consequence,
  stated rather than fixed — a pre-run settings step would put developer
  machinery in front of the player.
- Extends the play-screen frame only by its entry point.

---

## Phase 11 — Release: observability and documentation

**Milestone.** Every **chat-model** call is traceable in Langfuse when tracing
is enabled, and the documentation lets a stranger run and understand the agent,
with worked examples and the reasoning behind the technical decisions.

**Capabilities landed.** The Langfuse callback wiring on the seam; the module
docs completed and `docs/README.md`'s index brought up to date; the tool
reference; the content authoring guide; usage and worked examples; the
`requirement-map.md` correction; the remaining `general/` corrections.

**What a reviewer sees working.**

- A played turn appearing as a trace tree in Langfuse — **its chat-model calls,
  and only those.** Embedding calls are absent by nature, not by omission:
  LangChain's embeddings class emits no callback events, as `.env.dist` already
  states, so phase 4's ingestion and phase 6's journal writes are outside the
  trace and the milestone does not claim otherwise.
- **A fresh-checkout run-through reaching a named end state**, following the
  documentation alone. Not "the docs exist" — the docs work, and the end state
  is named so the claim is refutable.

**Pays into.** **Requirement 5**, which is graded. **Hard-2 as insurance**
alongside Hard-1.

**Dependencies.** Split, deliberately: the **Langfuse half needs phase 2**; the
**documentation half needs phase 10**, because it cannot document the drawer
before it exists. Recording it as "depends on everything" would hide
schedulable work.

**Open decisions owned.** None.

**Doc corrections owned.** `general/requirement-map.md`'s optional-task table —
the corrected bonus slate; **Langfuse counted as insurance and scoped to
chat-model calls only**; **Medium-2 banked by the checkpointer alone** in phase
7, with the journal strengthening it; **Medium-8 requiring both halves**, so
neither phase 8 nor phase 10 banks it alone; and **Medium-3 recorded as
considered and not claimed, with the reasoning**, because a reviewer who sees
the judgement scores it better than one who sees an overreach. Also the full
argument for [README.md](README.md) §7's requirement-3 reading, which now has
to cover internal plumbing and headless backends rather than only operator
CLIs. And `general/architecture.md`'s "Current state: scaffolding … the game
agent does not [exist]", which by this phase is no longer true.

**Inherited constraints.** Module documentation is a **per-phase obligation**,
so this phase completes and cross-checks the set rather than authoring it from
scratch. If it finds itself writing ten module docs, an earlier phase skipped
its own.
