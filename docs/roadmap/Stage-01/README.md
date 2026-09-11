---
title: "Stage-01 — the MVP single-player release"
stage: 1
created: 2026-09-10
---

# Stage-01 — the MVP single-player release

The stage-level contract for Stage-01: the release that satisfies `135.md`.
The phase plan itself — goals, preparation, steps — is
[phases.md](phases.md); this document holds what the plan deliberately does
not carry: the dependency reasoning, the scope fence, the requirement mapping,
and the two registers.

The design this stage builds is
[app-vision.md](../../general/app-vision.md),
[architecture.md](../../general/architecture.md) and
[model.md](../../general/model.md); the graded brief it pays into is `135.md`
at the repository root, mapped in
[requirement-map.md](../../general/requirement-map.md). The planning vocabulary
— stage, phase, milestone, step — is in
[glossary.md](../../general/glossary.md) under *Planning terms*, and the rules
for writing a plan at this altitude belong to the `planner` agent.

Where this document and the code disagree, the code wins and this document
gets corrected.

**This stage carries no concrete database schema and no API structure.**
Tables, columns, routes, payload shapes and module placement are pinned by step
specs, not here.

## Starting point

Phase 0 is landed: both trees scaffolded, the `auth`, `users` and `health`
backend modules, server-side sessions with CSRF, i18n, the generated typed
client, MUI v9, a blank authenticated home page, the compose stack and the
`cli`-profile one-offs. Its binding decisions are
[phase-0/shared-knowledge.md](../phase-0/shared-knowledge.md), which remains in
force across Stage-01.

Nothing of the game exists: no content, no prompts, no agent, no RAG, no game
modules. LangChain, LangGraph and pgvector's Python package are **not** yet
declared in `backend/pyproject.toml`.

## 1. Capability inventory

Every capability Stage-01 needs, and the phase that lands it.

| Area | Capability | Phase |
|---|---|---|
| Content | Content schema and loader — version-pinned reads, load-time referential validation | 1 |
| Content | The authored set — one campaign, one adventure, ≥3 scenes, definitions, a prose intro per adventure, a seed player character | 1 |
| Content | Content validation CLI | 1 |
| Provider | The OpenRouter seam — one credential, one failure classification, carrying chat, embedding and image calls | 2 |
| Provider | Prompt-asset resolution and the root convention it resolves against | 2 |
| Provider | Checkpointer provisioning and its exclusion from Alembic | 2 |
| Mechanics | Dice — expression parse, RNG, visibility flag; no model, no database | 3 |
| Knowledge | SRD rule ingestion into pgvector | 4 |
| Knowledge | Rule lookup — similarity search returning passages with citable sections | 4 |
| Runs | Runs — start, list, open, archive, unarchive, resume, and the per-run settings store | 5 |
| Runs | Object state, its validated write path, and scene placement and advance | 5 |
| Runs | Event stream and cost accounting — append-only, visibility-filtered, cost is a sum | 5 |
| Knowledge | Journal memory — written, embedded, retrieved by similarity plus the most recent N | 6 |
| Reasoning | Character generation agent, its prompt, and portrait media with a deterministic placeholder | 7 |
| Reasoning | The interrupt convention and the graph-thread convention | 7 |
| Frontend | App shell, playthrough browser, character creation screen, character sheet / state display | 7 |
| Reasoning | Dungeon Master agent and its full tool registry | 8 |
| Reasoning | Prompt composer, the guard, the turn transport over SSE, turn failure and recovery | 8 |
| Reasoning | The tool-error convention | 8 |
| Frontend | Play-screen frame, narration pane, composer, trace pane and every renderer, journal view | 9 |
| Frontend | Developer drawer | 10 |
| Release | Langfuse tracing on chat-model calls | 11 |
| Release | Release documentation — usage, worked examples, tool reference, content authoring guide | every phase; completed 11 |

### Pinned rulings

Recorded so they are not re-litigated a level down. Everything else about
placement is the architect's.

- **There is no agent base class, and none is to be created.** Two LangGraph
  graphs with different node sets, tool sets and termination conditions share a
  *library*, not a base. Agents are created when needed.
- **Prompt assets live with the capability that uses them**, resolved by an id
  namespaced to that capability. There is no single prompt root.
- **Phase 2 lands no module.** Everything in it is infrastructure by nature, so
  promotion on evidence ([D1](../phase-0/shared-knowledge.md)) does not apply.
- **Dice live with their only caller from the start** — the DM's `roll_dice`
  binding is the sole consumer, forever.
- **There is one character state display, owned by phase 7 and extended by
  phase 9.** No second state pane.
- **Character generation does not stream.** Its dialogue is short and
  turn-taking; SSE has one consumer.
- **The interrupt convention is pinned in phase 7 and reused verbatim in phase
  8.** It is a convention, not a promoted file, so nothing moves later.
- **The DM writes the journal itself, through a tool.** No chronicler agent, no
  second writer.

## 2. Dependency graph

**Build dependency** — cannot land or pass its own tests without it.
**Demo dependency** — lands and passes tests, but a reviewer cannot see the
point until the other exists.

```
Content schema & loader ──> the authored set (it validates it),
                            runs (pin + eager instantiation),
                            the get_scene / get_monster bindings

OpenRouter seam ──> SRD ingestion, journal memory, character generation,
                    DM agent, portrait media, observability
Checkpointer + thread convention ──> character generation's dialogue,
                                     the DM loop

Dice ──> the roll_dice binding

Runs ──> object state + validated writes, event stream, journal memory,
         character generation (somewhere to write the sheet),
         the run-settings store
Object state ──> scene placement and advance, the state display,
                 the update_object binding
Event stream ──> cost accounting, trace pane, turn failure & recovery

SRD ingestion ──> rule lookup ──> the lookup_rule binding
Journal memory ──> the journal bindings
Interrupt convention (7) ──> the ask_player binding (8)

DM agent's wire contract ──> play screen
Run settings + prompt composer ──> developer drawer
App shell ──> playthrough browser, character creation, play screen, drawer
```

### The load-bearing distinctions

- **A tool binding is not a build dependency of the service it exposes — the
  direction is reversed.** Each binding depends on the tool registry, which
  exists only in phase 8. This single fact is the basis of the whole ordering:
  it is what lets dice, rule lookup and journal memory land as finished
  services in phases 3, 4 and 6 while their bindings arrive together in 8.
- **Phases 1–6 and 8 are demo-dependent on a later phase for a screen; none of
  them is build-dependent on one.** Each has its own falsifiable evidence at
  command or wire level, and [phases.md](phases.md) names the phase that
  surfaces it.
- **Dice, rule lookup and journal memory are demo dependencies of nothing.**
  Each is provable on its own terms; the agent makes them *useful*, not
  *verifiable*.
- **The authored set is a demo dependency of the DM agent** and a build
  dependency of nothing: the loader validates a schema, not a campaign.
- **Phase 5 is headless by design, and phase 7 surfaces it.** A run no player
  can start is not a gap — it is what makes "no character, no game" true by
  construction, since the player-facing way to begin a run only ever ships
  alongside character creation.
- **The developer drawer is buildable after 5 and 8 and demonstrable only after
  9**, because its entry point hangs on a play-screen frame.
- **Character generation's cost events are what make phase 9's run total a true
  sum.** Phase 7 is the first writer to the event stream.

## 3. Parallelism

- **Group A = {1, 2, 3}** — three phases depending on nothing but phase 0.
  **They share one file: `backend/app/cli.py`**, where all three register a
  command. It needs an explicit order or a single owner for the registration
  lines. The hazard is the registrations, not the commands.
- **Group B = {4, 5}** — disjoint domains.
- **Group C = {6, 7}** — disjoint.
- **The tail 8 → 9 → 10 → 11 is a *build* order, not a calendar order.**
  [D11](../phase-0/shared-knowledge.md) pins the wire contract as a committed
  `frontend/openapi.json`, so phase 9 is speccable and testable against phase
  8's contract while phase 8 is still being built. What is strictly serial is
  landing, not specifying.
- **The revision chain is linear.** Group B's two phases would otherwise stack
  revisions on the same `down_revision` while both adding a line to
  `alembic/env.py`, and phases 6 and 7 both alter phase 5's tables — so the
  phases are assigned an explicit revision order and each rebases onto the
  previous head. The hazard is the heads, not the migration content.

**Longest chain of build dependencies:** 1 → 5 → 7 → 8 → 9 → 10 → 11, seven
deep.

## 4. Two verdicts worth keeping

**Mechanics first, bindings with the agent.** The question was whether to land
tools before the agent, or a "dumb" agent first. Neither: the deterministic
service and the tool binding that exposes it to a model are two different
artefacts, and they belong in different phases. Dice, the validated write path,
SRD search and journal write/retrieve are all independently testable with no
model in the loop. The binding is a thin adapter with no consumer until a
registry exists to receive it. So the services land in phases 3, 4 and 6, and
**there is no dumb-agent stage** — the agent arrives once, in phase 8, with its
full tool set. Three things pay for it: the DM's system prompt is never written
to accommodate absent dice and then rewritten; the guard ships in the same
phase as the loop it guards; and the trace renderers are written once. **The
accepted cost is that phase 8 is the largest milestone in the stage**, and the
only dependency-correct relief available is the one taken — splitting the
frontend off as phase 9 along the wire contract.

**Truncation fragility.** Bottom-up ordering front-loads the safe work and
back-loads the graded work. This is stated, not designed around.
**Medium-1's cost display lands in phase 9 and Medium-8's developer/player
split lands in phase 10 — those are the two items to protect if the stage is
ever cut short.** Stopping after phase 9 loses Medium-8 entirely; stopping
after phase 8 loses Medium-1's display too. The flip side is a real gain: only
phases 7, 9 and 10 touch a frontend surface at all, and no phase edits a trace
dispatch point a second time.

## 5. Scope fence

| Out of Stage-01 | Reason |
|---|---|
| **Combat as a simulated system** — no encounter entity, no initiative order, no round or turn tracking, no turn-order pane | Game design, not agent knowledge: a fight resolves with dice and consequences, and nothing in `135.md` grades initiative |
| **The LLM content-generation CLI** and its prompt asset | Content is hand-authored for Stage-01, so the generator has no caller; the content-version machinery already admits more content later |
| **A quick-start that skips character creation** | Creating a character is how a run begins, so a path around it is a second way to start a run with no requirement behind it. The content's seed character survives as a fixture, not as a player-facing option |
| **Streaming anywhere but the DM's narration** | Character generation's dialogue is short and turn-taking, so a second streaming consumer would buy latency cover nobody feels |
| **Turn cancellation** | Retry on a *failed* turn covers the real need; a mid-stream abort is a second control path with no graded requirement behind it |
| **Retrying a completed turn** | A finished turn is canon — re-rolling it would make the dice negotiable |
| **A timed undo on archive** | Archive is reversible by an explicit unarchive with a confirm, which is simpler and has no timer to get wrong |
| **Portrait-only reroll, and unbounded character regeneration** | One reject-and-re-derive before acceptance is enough to feel in control; more turns a creation flow into a slot machine |
| **Purge (hard deletion of archived runs)** | An operator convenience; archive is the player-facing gesture and nothing in `135.md` needs hard deletion |
| **`app sessions prune`** (phase-0 known future work) | Expired sessions are already treated as absent; unbounded row growth is not a graded concern |
| **Multiplayer, maps, voice** | The vision places them in a later capstone |
| **A second adventure or campaign** | One is the stated initial content set, and a new content version adds more without a migration |
| **User-level settings or an override chain** | Settings live on the run; a second layer has no caller |
| **An abstract agent base** | Nothing shared exists to put in it: agents are created when needed |
| **Medium-5 / Hard-4 — feedback loops and learning from feedback** | The bonus slate is already met with insurance |
| **Medium-6 — plugin system and player-toggleable tools** | Same, and a DM whose dice tool can be switched off stops being trustworthy |
| **Medium-7 — multi-model support beyond OpenRouter model selection** | Model choice through one seam already covers the intent; a second provider adds a credential and no evidence |
| **Hard-3 — a Ragas / DeepEval evaluation report** | Same, and it measures quality this stage has no baseline for |
| **Hard-5 — integrating external data sources** | The SRD corpus and the authored content are the domain's knowledge, both shipped in-repo and pinned by version; fetching live data would make a save unreproducible |
| **Easy-5 — an interactive help chatbot** | The DM *is* the conversational surface; a second chatbot is redundant UI |
| **Easy-1 — asking ChatGPT to critique the solution** | Not a feature, so it cannot be a milestone; it is a review activity belonging to whoever prepares the submission |

## 6. Requirement and bonus mapping

### `135.md` task requirements

| # | Requirement | Banked by |
|---|---|---|
| 1 | Agent purpose, usefulness, target users | [app-vision.md](../../general/app-vision.md), restated in phase 11's documentation |
| 2 | Core functionality, primary tasks, user interactions | Phase 7 (the creation dialogue) and phase 8 (the turn, its tools and its interrupt) |
| 3 | A user-friendly UI for every functionality | Phases 7, 9 and 10 — read as stated in §8 below |
| 4 | Appropriate tools, error handling, real-world usage | Phases 2 (provider failures), 3 (invalid expressions), 4 (empty retrieval), 5 (rejected writes), 8 (turn failure and recovery, refusals) |
| 5 | Documentation: usage, examples, technical decisions | Every phase's module doc; completed and proven by phase 11's fresh-checkout run-through |

### Optional tasks targeted

| Brief task | Mechanic | Banked by |
|---|---|---|
| **Medium-1** — token usage and cost | Summed from the event stream; per turn on the trace row, run total in the play-screen header and on the list row | Stream at 5, first real figures at 7, **display at 9** |
| **Medium-2** — long **or** short-term memory | The checkpointer (short) · journal entries with similarity-plus-recency retrieval (long) | **Phase 7 banks it** — the brief says "long-term *or* short-term", and the character agent is the checkpointer's first consumer. Phase 6's journal **strengthens it rather than completing it** |
| **Medium-8** — a security guard, **and** developer settings kept out of the player experience | The guard node · the developer drawer | Phases 8 **and** 10 together. The brief conjoins the two, so **neither banks it alone and phase 10 is not droppable** |
| **Hard-1** — agentic RAG | The DM decides whether to look a rule up and may re-query | Corpus at 4, **the agency at 8**, the citation visible at 9 |
| **Hard-2** — LLM observability | Langfuse tracing of every **chat-model** call, counted as **insurance** rather than as the primary hard task | Phase 11 |
| Easy-2 — personality | DM tone per run | Phase 8 (the fragments and the composer) + phase 10 (the selection) |
| Easy-3 / Easy-4 — model choice and settings | Model and temperature in the drawer | Phase 10 |
| Medium-4 — authentication and personalisation | Landed auth plus per-run settings | Phase 0 + phase 5 |

**Medium-3 — an extra function tool calling an external API — is considered
and not claimed.** The portrait call is a one-shot step inside character
generation rather than a tool in an agent's registry, and it reaches the same
OpenRouter credential the model already uses, so both halves of the claim
would be a stretch. The slate above already exceeds ≥2 medium + 1 hard.
Phase 11 records the reasoning in
[requirement-map.md](../../general/requirement-map.md), because a reviewer who
sees the judgement scores it better than one who sees an overreach.

## 7. Open-decisions register

Recorded, not settled. **This register is the single home for them** — the
phase plan carries an investigation line, not a decision. Each is settled in
the owning phase's step spec.

| Open decision | Owning phase |
|---|---|
| Where the cost figure comes from — a static price table in settings, or OpenRouter's usage-accounting field. **Trap: the static-table branch needs new declared settings that `.env.dist` has no entries for, and `.env.dist` is owner-only** | 2 |
| **The failure-injection seam** — how a provider failure is produced on demand: an unreachable base URL, a bogus model id, an injected timeout. A bad key is producible by editing `.env`; phase 8's timeout evidence and phase 7's image-failure evidence are not. Phase 2 defines one seam and both reuse it | 2 |
| Whether LangChain's OpenAI-compatible embeddings class can be pointed at the OpenRouter base URL, and so whether the seam's embedding side is a configuration of that class or a thin call of its own. Use `mcp__context7`; do not decide it from recall | 2 |
| **How the migration expresses the vector width — and only that.** `.env.dist` already pins the embedding model, states its native size, states that no `dimensions` parameter is ever sent, and requires a migration to change it. **Phase 4 must not pick a different model: `.env.dist` is owner-only** | 4 |
| **How** a fixture-local real engine is driven — not whether one is allowed, which `backend-stack.md` already permits. Doing it against async SQLAlchemy collides with the landed "fully synchronous suite, no `pytest-asyncio`, no async fixtures" rule, so this **may amend a landed decision**. Phase 5 inherits the answer | 4 |
| Ownership of a run: a membership row, or a user id on the run. **`model.md` and `architecture.md` currently rule for the membership row** — phase 5 may overturn that ruling, and §9 records the correction it must then make | 5 |
| The adventure's progress: its own entity, or fields on the run. **`model.md` currently rules for a separate entity** — same condition | 5 |
| The object state models and their read surface: their own module, or a service inside `playthrough` | 5 |
| The journal's retrieval policy — top-k plus the most recent N unconditionally, classification kept, weighted ranking dropped as unmeasurable against one adventure of data | 6 |
| The character capability: its own module, or a service inside `playthrough` | 7 |
| What triggers the deterministic portrait placeholder | 7 |
| The exact wording of the i18n carve-out: **agent-authored content — narration, citations, option labels, journal facts — is verbatim model output and is exempt from the i18n-key rule.** Owned here because the character sheet is the first model output rendered | 7 |
| The agent-progress milestone vocabulary, bound by the constraint that **nothing in the stream may reveal that a hidden roll happened** | 8 |
| The in-stream error representation. **Ruled: one error shape, two transports** — a turn failing after the 200 terminates the stream with an event carrying the same `{code, message, details}` object, so D4's single shape holds. Phase 8 pins the remaining transport detail | 8 |
| **What passes through the guard's override hook.** The free-text system-prompt override sits in the system position, upstream of everything a turn-inspecting guard reads, so this decides whether Medium-8's claim holds. **Phase 8 owns leaving the hook; phase 10 owns the policy, and the architect settles it, not the implementer** | 10 |
| **How `hidden` and `Secret.dc` are projected out of any scene-derived tool result** before it reaches the visible trace. Content carries DM-only secrets and their difficulty; a tool result that passes a `Scene` through unfiltered leaks both, and "the fact that a roll happened is not a tell" fails. Recorded by phase 1 (`roadmap/Stage-01/phase-01/shared-knowledge.md` §10.3) | 8 |

## 8. The requirement-3 reading

`135.md` requirement 3 asks for "a user-friendly interface for all
functionalities". Stage-01 reads that as **every *player* capability has a
surface** — and bottom-up ordering makes this reading carry weight, so it is
argued rather than asserted.

**Seven of eleven phases end without a screen: 1, 2, 3, 4, 5, 6 and 8.** They
fall into three kinds, and only the first is the familiar operator argument.

- **Operator capabilities** — SRD ingestion (4) and content validation (1).
  Run once by whoever deploys the system, never by a player. `135.md`'s own
  framing, "your user may not be that familiar with LLMs", is about the player,
  and giving these screens would put developer machinery inside the player
  experience — precisely what Medium-8 penalises.
- **Internal plumbing** — the OpenRouter seam and prompt assets (2), dice (3).
  Nobody drives these directly at all; they are reached through a capability
  that does have a surface.
- **Headless backends** — runs and object state (5), journal memory (6), and
  the DM turn (8). These *are* player capabilities, and **this document does
  not claim otherwise.** They ship without a surface because the dependency
  graph puts the surface in a later phase, and the surface ships in that phase.
  The claim is that the capability has a surface **in Stage-01**, not in the
  phase that built it.

The surfacing phases are 1 → 7 and 8 · 2 → 8 and 10 · 3 → 8 and 9 · 4 → 9 ·
5 → 7 · 6 → 9 · 8 → 9. Phase 11's documentation makes the argument explicitly,
so a reviewer meets it rather than discovering a gap.

## 9. Doc-correction register

Contradictions between the existing `docs/general/` design and this plan.
**This register is the single home for them**; each is corrected by the phase
that owns the change — not batched into phase 11 — because a doc describing a
capability the phase just changed is the phase's own output.

| Contradiction | File | Owning phase |
|---|---|---|
| The static-file tree's content root, the `npcs/` + `monsters/` split, the scene-field line, the missing `intro` / `entry_scene` / seed character, and the unstated version mechanism — enumerated in `roadmap/Stage-01/phase-01/shared-knowledge.md` §9.2 | `general/model.md` | 1 |
| "Authored by an LLM once through a `generate_adventure` CLI that prompts with the SRD and enforces the schema" — content is hand-authored | `general/architecture.md` | 1 |
| The tool table's `get_monster(name)` row — with one `Definition` entity the binding is id- or name-addressed over `definitions`, and its final name and argument are phase 8's to pin | `general/architecture.md` | 8 |
| Requirement 3's wording does not state the player-capability reading | `general/requirement-map.md` | 1 (states it) · 11 (full argument) |
| `docs/modules/` does not exist and `docs/README.md` says "None yet" | `docs/README.md`, `docs/modules/` | every phase; first entry lands with 1 |
| The static-file tree lists a content-generation prompt asset that will not exist, **and pins the only prompt root as `game`'s directory** — which would place the character-generation prompt inside `game` even if the character capability becomes its own module, a module-boundary violation. The correction is the root convention: an id resolves against its owning capability's own prompt directory | `general/model.md` | 2 |
| "LangChain / LangGraph are declared but not wired yet" — they are not declared | `general/backend-stack.md` | 2 |
| D7's "exactly five settings" — **one amendment, not two**: the OpenRouter key, the chat, embedding and image models and the embedding dimension all become declared fields together, because all three call kinds land on one seam in one phase | `roadmap/phase-0/shared-knowledge.md` | 2 |
| The suite is "fully synchronous … no `pytest-asyncio` and no async fixtures", which a fixture-local async engine collides with. **A possibility, not a certainty**: if phase 4 needs one, it amends this landed decision rather than working around it | `general/backend-stack.md`, `roadmap/phase-0/shared-knowledge.md` | 4 |
| The combat paragraph, the encounter node in the entity diagram, "Encounter hangs off AdventureRun", and the encounter line in the lifecycle table | `general/model.md` | 5 |
| The **Encounter** run-term entry, and the **Initiative** game term, which now has no caller | `general/glossary.md` | 5 |
| Player-experience §3's "turn order beside the narration" | `general/app-vision.md` | 5 |
| The web-client bullet's "state panel (HP, AC, inventory, turn order)" | `general/architecture.md` | 5 |
| The lifecycle table's **Purge** row describes a capability §5 fences out of Stage-01 | `general/model.md` | 5 |
| **A confirmation, not a correction.** The lifecycle table's "generate the player's creature" on starting a playthrough is **correct as written** — phase 7 does exactly that, which is why character creation and the run are adjacent rather than swapped. Only the **seed character's fixture role** needs stating: it exists so phase 5 has a character before the generation agent lands | `general/model.md` | 5 |
| Nothing names a **seed player character**, so the fixture role above has no term | `general/glossary.md` | 5 |
| **Conditional, and it must be resolved either way.** "Ownership lives on the membership row" is written as a *ruling* in one file and repeated in the other, while §7 records it as an *open decision*. If phase 5 overturns it, phase 5 corrects both files; if phase 5 upholds it, phase 5 records that the decision is closed. **A phase-5 architect must not be left reading two documents that disagree about whether there is a choice** | `general/model.md`, `general/architecture.md` | 5 |
| **Conditional, same condition.** `AdventureRun` is written as a full entity with its own justification, while §7 records it as an open decision. Overturn and correct, or uphold and close | `general/model.md` | 5 |
| "Every user-facing string goes through a key; a literal in a component is a defect" needs the carve-out for **agent-authored content, which is verbatim model output** | `general/frontend-stack.md` | 7 |
| The tool table's `start_combat()` / `end_round()` rows | `general/architecture.md` | 8 |
| The wire convention describes only resource objects and one error envelope; SSE is a third response kind. **State affirmatively that D5 is not amended** — a long-lived SSE response is still one request, so "request-scoped or a CLI one-off" still holds | `general/architecture.md` | 8 |
| "`ask_player` **every turn**" — the DM asks when the decision is the player's, and one that asked every turn would not be narrating | `general/requirement-map.md` | 8 |
| The optional-task table: the corrected bonus slate; **Langfuse counted as insurance and scoped to chat-model calls only**; **Medium-2 banked by the checkpointer alone**, with the journal strengthening it; **Medium-8 requiring both halves**; and **Medium-3 considered and not claimed, with the reasoning** | `general/requirement-map.md` | 11 |
| "Current state: scaffolding … the game agent does not [exist]" | `general/architecture.md` | 11 |
