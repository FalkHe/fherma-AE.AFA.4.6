---
title: "Stage-01 — the MVP single-player release"
stage: 1
created: 2026-09-10
---

# Stage-01 — the MVP single-player release

The stage-level contract for Stage-01: the release that satisfies `135.md`.
Per-phase detail — milestones, evidence, owned decisions — is
[phases.md](phases.md). The design this stage builds is
[app-vision.md](../../general/app-vision.md),
[architecture.md](../../general/architecture.md) and
[model.md](../../general/model.md); the graded brief it pays into is `135.md`
at the repository root, mapped in
[requirement-map.md](../../general/requirement-map.md).

Where this document and the code disagree, the code wins and this document
gets corrected.

## Terminology

- A **Stage** is a release. Stage-01 is the MVP.
- A Stage decomposes into **Phases**. Each phase ships exactly one
  **Milestone**: a finished, self-contained piece of functionality, falsifiable
  by evidence a reviewer can produce. A phase's completion *is* its milestone.
- A phase decomposes into **Steps**, each with its own step spec and its own
  phase directory. **Steps are not defined at this altitude and no phase
  directory exists yet**; both arrive when the phase is specced.
- This stage carries **no concrete database schema and no API structure**.
  Tables, columns, routes and payload shapes are pinned by step specs.

## Ordering principle: bottom-up

Phases are ordered by the **dependency graph**, not by what is visible in a
browser. A phase whose milestone is a command or a tested service with no
screen is correct if that is where the graph puts it; the order is not
contorted to manufacture visibility. Two things do not relax: a phase ships
one **finished** capability — no half-capabilities parked for a later phase —
and every milestone is **falsifiable**.

The consequence is stated rather than hidden: **seven of eleven phases end
without a screen**, the first player-visible milestone is phase 7, and the
first turn a player can take in a browser is phase 9. See §3 and §7.

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

## 1. Capability inventory and classification

Every capability Stage-01 needs, with its placement justified against
[architecture.md](../../general/architecture.md)'s modular rules and
[D1](../phase-0/shared-knowledge.md) — promotion on evidence (two or more real
module callers), and one module never importing another module's internals.

### Provider access and prompt plumbing

**Phase 2 lands no module at all.** Everything in it is `core/` infrastructure
by nature — provider access, the checkpointer, prompt-asset resolution — so
there is no module for a single-caller version to live in and promotion on
evidence does not apply to it.

| Capability | Placement | Why there | Phase |
|---|---|---|---|
| **The OpenRouter seam** — the one place the credential lives and provider failures are classified, carrying **chat, embedding and image** calls | `core/` singleton | The per-app-singleton carve-out, same class of object as the HTTP client and the DB engine. One seam means one credential site and one failure-classification site; a second of either would be a second way to do the same thing. All three call kinds land together, which is why **D7 is amended once, not twice** | 2 |
| **Prompt-asset resolution** — an id to prompt text on disk, and **the root convention it resolves against** | `core/`, with the seam | Genuinely shared by both agents and identical for both: one function, two real callers (phases 7 and 8). Phase 2 has no module to put it in. **The root convention:** an id is namespaced by its owning capability and resolves against *that capability's own* prompt directory — so a `core/` resolver needs no knowledge of any module, and prompts still live in the module that uses them | 2 |
| **Prompt assets** — the base DM prompt, the personality fragments, the character-generation prompt | **With the capability that uses them**, per the root convention above — never all under one module's directory | `model.md` currently pins the only root as `game`'s prompt directory, which would put the character-generation prompt inside `game` even if the character capability becomes its own module: a module-boundary violation. Phase 2 owns the convention and proves the resolver against a fixture; the shipped assets land with their agents | convention 2 · assets 7, 8 |
| **Checkpointer provisioning** — the LangGraph Postgres checkpointer's own setup and its exclusion from Alembic | `core/` singleton + an Alembic configuration change | No job runner exists to call `setup()`, and a stray autogenerate would try to drop the schema | 2 |
| **The graph-thread convention** — how a graph thread relates to a run | A **written ruling, owned by its first consumer** | **Not phase 2's**: no run exists there for a thread id to derive from, so the convention would be unprovable where it was written. Phase 7 pins it and proves it — a pending question surviving a reload *is* the thread resolving across a process boundary — and phase 8 reuses it | 7 → 8 |
| **The tool-error convention** — how a tool signals a domain failure so the model can recover instead of the turn dying | A **written ruling and a shape**, not a file, **owned by its first consumer** | **Not phase 2's** either: it gets no executable proof until bindings land on it, and a convention with no producible evidence in the phase that writes it fails this stage's own falsifiability rule. This is the one real residual of the mechanics-first verdict, and the honest fix is to write it where it is first exercised | 8 |
| **An agent base class** | **Does not exist and must not be created** | Two LangGraph graphs with different node sets, different tool sets and different termination conditions share a *library*, not a base. Agents are created when needed | — |

### Reasoning

| Capability | Placement | Why there | Phase |
|---|---|---|---|
| **Character Generation Agent** — a described idea plus a follow-up or two becomes a sheet | **Open** — own module `character`, or a service inside `playthrough` | Undecidable at this altitude; see the open-decisions register | 7 |
| **The interrupt convention** — the wire shape of a pending human-in-the-loop decision and how it resumes | A **pinned convention**: phase 7 pins it, **phase 8 reuses it verbatim** | The character agent's clarifying dialogue is the first consumer and the DM loop is the second, so the convention is proven on a two-question dialogue rather than inside a nine-tool loop. A convention, not a promoted file, so nothing moves | 7 → 8 |
| **Portrait Media** — an OpenRouter image call, stored once to the media volume, served by a static route, with a deterministic placeholder | Service inside the character capability's owner, plus a static route and a Docker volume | Only caller | 7 |
| **Dungeon Master Agent** — the LangGraph loop and its full tool registry | Services inside `game` | The tool layer is the module's public verb surface; each binding delegates to a service that already landed and contains no SQL | 8 |
| **Prompt Composer** — base DM prompt + personality + optional run override | Service inside `game`, **not shared** | The character agent has one prompt file and nothing to compose, so composition has exactly one caller | 8 |
| **Guard** — refuses prompt injection and out-of-band state claims | Service inside `game` | Single caller, wired as the node in front of the loop, **in the same phase as the loop it guards** | 8 |
| **Turn Transport** — the SSE stream carrying narration and agent-progress milestones | Service + route surface inside `game` | It is the turn's response, so it belongs to the turn's owner. **Character generation does not stream** — its dialogue is short and turn-taking, so SSE has one consumer | 8 |
| **Turn Failure & Recovery** — a turn that dies mid-flight leaves state consistent, preserves the input and is retryable | Cross-cutting behaviour of the loop, inside `game` | A property of the loop, not a separate component | 8 |

### Content

| Capability | Placement | Why there | Phase |
|---|---|---|---|
| **Content Schema & Loader** — content models, version-pinned reads, load-time referential validation | Backend module `content` | A module is a domain, not a table: it owns models, schemas, a read surface and a service, and `playthrough` and `game` consume it through that service | 1 |
| **Authored Content Set** — one campaign, one adventure, ≥3 scenes, definitions, an authored prose `intro` per adventure, and a **seed player character** | Content asset in git, mounted read-only | Not code; reviewed as a diff | 1 |
| **Content Validation CLI** | Typer one-off in `content` | Not a request, and D5 leaves the CLI as the only non-request seam | 1 |

### Mechanics

| Capability | Placement | Why there | Phase |
|---|---|---|---|
| **Dice & Mechanics** — expression parse, RNG, visibility flag; deterministic, no LLM, no database | A module of pure functions **inside `game`**, which phase 3 therefore creates and phase 8 completes | Its only caller, forever, is the DM's `roll_dice` binding, so promotion on evidence puts it with that caller from the start. Placing it in `core/` would be speculative; giving it a module of its own would create one that later gets folded | 3 |
| **Runs** — start (pin campaign and content version, ownership, eager object instantiation), list, open, archive, unarchive, resume, and the per-run settings store | Backend module `playthrough` | Clear domain owner; settings live on the run, so the run owns them | 5 |
| **Object state, its validated write path, and scene placement and advance** | **Open** — own module, or a service inside `playthrough` | Undecidable at this altitude; see the register. Placement and advance land together here, because the validated write path is in the same phase — position is object state, so advancing it is a validated write, so there is no writer-without-a-write-path to hold the advance back from | 5 |
| **Event Stream & Cost Accounting** — the append-only stream of narration, input, rolls, tool calls, errors and cost; visibility-filtered on read; run cost is a sum, never a column | Backend module `events` | Distinct lifecycle (append-only, never pruned), and it is the run's own aggregate, so it lands with the run | 5 |

### Knowledge

| Capability | Placement | Why there | Phase |
|---|---|---|---|
| **SRD Rule Ingestion** — chunk and embed SRD 5.1 into pgvector | Typer CLI one-off in `rules` | One-time, not a request | 4 |
| **Rule Lookup** — similarity search returning passages with citable sections | Service inside `rules` | Phase 8's `lookup_rule` binding calls it; bindings contain no SQL | 4 |
| **Journal Memory** — durable canon written, embedded and retrieved by similarity plus the most recent N unconditionally | Backend module `journal` | Own table and own lifecycle (it cascades with the run); phase 8's journal bindings call its service | 6 |

### Frontend

| Capability | Placement | Why there | Phase |
|---|---|---|---|
| **App Shell & Navigation** | Promoted from `modules/home` to `src/components/` — **earned, not speculative** | At phase 7 it has two real module callers; the promotion holds **only if the shell keeps its `action?: ReactNode` slot pattern and imports from no module**, per D1's worked example. Phase 7 adds navigation, which is exactly where sign-out and current-user creep in and disqualify it | 7 |
| **Playthrough Browser** — list, open, archive filter, unarchive | Frontend module `playthrough` | | 7 |
| **Character Creation screen** | Frontend module `character` | Mirrors its backend owner and is its only caller | 7 |
| **Character sheet / state display** — the sheet after creation, and the live state pane during a turn | A component in frontend `character`, **one owner**, extended at phase 9 | Its only caller at phase 7. Phase 9's play screen becomes the second caller and imports it as a **named cross-module surface** rather than reaching into it, and adds live updates to it. There is no second state pane in `game` | 7, extended 9 |
| **Term-explanation pattern** · **Failure pattern** | Components in frontend `character`, **promoted to `src/components/` unchanged at phase 9** | Textbook promotion on evidence: one caller at 7, a second at 9, promoted without a change | 7 → 9 |
| **Play-screen frame, Narration pane, Composer, Trace pane and every renderer, Journal view** | Frontend module `game` | One screen, one module, **built once**. The trace's renderers arrive with the events they render, so no later phase edits the dispatch point. The journal view is a component here, not a module: one read-only pane plus one hook | 9 |
| **Developer Drawer** — model, temperature, personality, one marked free-text prompt override, plus the composed prompt and pinned content version read-only | Frontend module `devtools` | **Not the same case as the journal view.** Medium-8 grades the developer/player separation *structurally*, so a separate module makes the fence a fact about the tree rather than a convention | 10 |

### Release

| Capability | Placement | Why there | Phase |
|---|---|---|---|
| **Observability** — Langfuse tracing on every **chat-model** call | `core/` wiring on the seam | One callback attached where the chat model is built; no new module. **Embedding calls are never traced** — LangChain's embeddings class emits no callback events, as `.env.dist` already states — so phase 4's ingestion and phase 6's journal writes are outside the trace by nature, not by omission | 11 |
| **Release Documentation** — usage, worked examples, the tool reference, the content authoring guide, decision records | `docs/modules/*.md` plus each module's `README.md` | Per-phase obligation, not a deferred batch: each module states its own intent, surface and quirks | every phase; completed 11 |

## 2. Dependency graph

**Build dependency** — cannot land or pass its own tests without it.
**Demo dependency** — lands and passes tests, but a reviewer cannot see the
point until the other exists.

### Build dependencies

```
Content Schema & Loader ──> Authored Content Set (it validates it),
                            Runs (pin + eager instantiation),
                            the get_scene / get_monster bindings

OpenRouter seam ──> SRD Ingestion, Journal Memory, Character Generation,
                    DM Agent, Portrait Media, Observability
Checkpointer + thread convention ──> Character Generation's dialogue,
                                     the DM loop

Dice ──> the roll_dice binding

Runs ──> Object state + validated writes, Event Stream, Journal Memory,
         Character Generation (somewhere to write the sheet),
         the run-settings store
Object state ──> scene placement and advance, the state display,
                 the update_object binding
Event Stream ──> Cost Accounting, Trace pane, Turn Failure & Recovery

SRD Ingestion ──> Rule Lookup ──> the lookup_rule binding
Journal Memory ──> the journal bindings
Interrupt convention (7) ──> the ask_player binding (8)

DM Agent's wire contract ──> Play screen
Run settings + Prompt Composer ──> Developer Drawer
App Shell ──> Playthrough Browser, Character Creation, Play screen, Drawer
```

### The load-bearing distinctions

- **A tool binding is not a build dependency of the service it exposes — the
  direction is reversed.** Each binding depends on the tool registry, which
  exists only in phase 8. This single fact is the basis of the whole reorder:
  it is what lets dice, rule lookup and journal memory land as finished
  services in phases 3, 4 and 6 while their bindings arrive together in 8.
- **Phases 1–6 and 8 are demo-dependent on a later phase for a screen; none of
  them is build-dependent on one.** Each has its own falsifiable evidence at
  command or wire level, and each names the phase that surfaces it.
- **Dice, Rule Lookup and Journal Memory are demo dependencies of nothing.**
  Each is provable on its own terms; the agent makes them *useful*, not
  *verifiable*.
- **The Authored Content Set is a demo dependency of the DM Agent** and a build
  dependency of nothing: the loader validates a schema, not a campaign.
- **Phase 5 is headless by design, and phase 7 surfaces it.** A run that no
  player can start is not a gap — it is the arrangement that makes "no
  character, no game" true by construction, since the player-facing way to
  begin a run only ever ships alongside character creation.
- **The Developer Drawer is buildable after 5 and 8 and demonstrable only after
  9**, because its entry point hangs on a play-screen frame that does not exist
  before then.
- **Character generation's cost events are what make phase 9's run total a true
  sum.** Phase 7 is the first writer to the event stream, so if generation and
  the portrait call did not record their cost the total would be quietly false.

## 3. Phases

| # | Phase | Milestone (shipped functionality) | Deps | Parallel with |
|---|---|---|---|---|
| 1 | Content schema and the authored set | A content schema exists and one campaign, one adventure, ≥3 scenes, its definitions, an authored prose intro per adventure and a seed player character are authored against it, load at a pinned version, and a validation command locates any referential error | 0 | 2, 3 |
| 2 | The OpenRouter seam and prompt assets | One seam carries chat, embedding and image calls on one credential with one failure classification; each round-trips and each fails cleanly and distinguishably; a prompt asset resolves by id against the root convention; the checkpointer's schema is provisioned and excluded from Alembic | 0 | 1, 3 |
| 3 | Dice and mechanics | Dice expressions parse and resolve deterministically with a visibility flag, and an invalid expression is rejected specifically. No model, no database | 0 | 1, 2 |
| 4 | SRD knowledge base | SRD 5.1 is ingested into pgvector and a rules query returns relevant passages with citable section references | 2 | 5 |
| 5 | Runs, object state and the event stream | A run exists, pins its content version, owns validated objects with a validated write path — including scene placement and advance — owns an append-only visibility-filtered event stream whose cost is a sum, and is listable, archivable and resumable | 1 | 4 |
| 6 | Journal memory | Facts are written, embedded, and retrieved by similarity plus the most recent N unconditionally | 2, 5 | 7 |
| 7 | Character creation, and how a run begins | A player signs in, describes a character in plain words, answers a follow-up or two, receives a finished sheet with a portrait, and lands in a run that is listed, archivable and resumable | 2, 5 | 6 |
| 8 | The DM turn | A turn runs end to end over the wire: plain words in, streamed narration out with progress milestones, real visibility-aware rolls, validated state changes and scene advance, cited rules, journal writes and recalls, an interrupt when the decision is the player's, injection and out-of-band state claims refused, every turn recorded with its cost, and a failed turn recoverable | 1, 2, 3, 4, 5, 6, 7 | — |
| 9 | The play screen | The player plays in a browser: narration, live state, a filtered trace carrying visible rolls, cited sections, retrievals, refusals and per-turn plus run cost, decision prompts, retry on a failed turn, and no roll row for a hidden roll | 8 | — |
| 10 | Developer drawer | Model, temperature, personality and one explicitly-marked free-text prompt override are changeable per run outside the player experience, with the composed effective prompt and the pinned content version shown read-only | 5, 8, 9 | — |
| 11 | Release: observability and documentation | Every chat-model call is traceable in Langfuse when enabled; the documentation lets a stranger run and understand the agent to a named end state | Langfuse: 2 · documentation: 10 | — |

### Parallel groups

- **Group A = {1, 2, 3}** — three tier-zero phases depending on nothing but
  phase 0: content assets and the `content` module, `core/` infrastructure, and
  pure dice functions. **They share one file: `backend/app/cli.py`.** All three
  milestones are commands — phase 1's validation, phase 2's round-trips, phase
  3's roll — and sub-apps are registered there at module scope, so that file
  takes three concurrent edits. It gets the same treatment as group B's
  `alembic/env.py`: an explicit order, or a single owner for the registration
  lines. The hazard is the registrations, not the commands.
- **Group B = {4, 5}** — disjoint modules, `rules` against `playthrough`.
- **Group C = {6, 7}** — disjoint, `journal` against the character capability
  and the frontend's first screens.
- **The tail 8 → 9 → 10 → 11 is a *build* order, not a calendar order.** D11
  pins the wire contract as a committed `frontend/openapi.json`, so phase 9 is
  speccable and testable against phase 8's contract while phase 8 is still
  being built — which keeps a frontend agent off the bench during the stage's
  largest milestone. What is strictly serial is landing, not specifying.
  Parallelism has otherwise moved from the tail to the head; see the truncation
  note below, because the tail is where the graded work is.
- **The revision chain is linear.** Group B's two phases would otherwise stack
  revisions on the same `down_revision` while both adding a line to
  `alembic/env.py`, and phases 6 and 7 both alter phase 5's tables — so the
  phases are assigned an explicit revision order and each rebases onto the
  previous head. The hazard is the heads, not the migration content.

**Longest chain of build dependencies:** 1 → 5 → 7 → 8 → 9 → 10 → 11, seven
deep.

### Verdict: mechanics first, bindings with the agent

The question was whether to land tools before the agent, or a "dumb" agent
first and add functionality to it. **Neither, exactly: the deterministic
service and the tool binding that exposes it to a model are two different
artefacts, and they belong in different phases.** Dice arithmetic, the
validated write path, similarity search over the SRD and journal
write/retrieve are all independently testable with no model in the loop, and
`architecture.md` already separates them into the Mechanics and Content layers.
The LangChain tool definition, by contrast, is a thin adapter with no consumer
until a registry exists to receive it — landing it early would ship a
half-capability whose only test duplicates the service's own. So they land as
services in phases 3, 4 and 6, and **there is no dumb-agent stage**: the agent
arrives once, in phase 8, with its full tool set.

This **reverses a split made in an earlier draft**, which staged a narration-only
loop and then added dice, interrupts, rule lookup and journal one phase at a
time. Three named benefits pay for the reversal:

1. **The DM's system prompt is never written to accommodate absent dice and
   then rewritten.** The staged order needed a prompt instructing the DM to
   narrate and defer because it had no way to resolve an outcome — throwaway
   work in the highest-risk asset in the stage.
2. **The guard ships in the same phase as the loop it guards**, closing a
   two-phase window in which a free-text-into-tool-calling loop shipped with no
   guard at all.
3. **The trace pane's renderers are written once** instead of by five phases in
   sequence, which removes the shared-surface churn entirely.

**The accepted cost: phase 8 is the largest milestone in the stage by a wide
margin.** It is one seam — loop, guard, prompts, composer, transport and the
whole tool registry — and the only dependency-correct relief available is the
one taken, splitting the frontend off as phase 9 along the wire contract.

### Truncation fragility, and the flip side

Bottom-up ordering **front-loads the safe work and back-loads the graded
work.** This is a stated property, not something to design around, and the
order is not reordered to hedge it.

- **Medium-1's cost display lands in phase 9 and Medium-8's developer/player
  split lands in phase 10. Those are the two items to protect if the stage is
  ever cut short.** Stopping after phase 9 loses Medium-8 entirely; stopping
  after phase 8 loses Medium-1's display too.
- **The flip side is a real gain, not a consolation.** In the staged order the
  loop shipped two phases before its guard, so the stage passed through a state
  with an unguarded free-text-into-tool-calling surface. **That window is
  gone**: phase 8 contains both.

### Surface growth

| Surface | Created in | Extended in |
|---|---|---|
| App shell and navigation | 7 | 9 (the play route), 10 (the drawer's entry point) |
| Playthrough browser | 7 | 9 (a run row leads to play) |
| Character creation screen | 7 | built once |
| Character sheet / state display | 7 | 9 (live updates during a turn) |
| Term-explanation pattern | 7 | 9 — promoted to `src/components/` unchanged on its second caller |
| Failure pattern | 7 | 9 — promoted likewise |
| Play-screen frame, narration pane, composer | 9 | 10 (the drawer's entry point only) |
| Trace pane and every renderer | 9 | built once |
| Journal view | 9 | built once |
| Developer drawer | 10 | built once |

**The collapse is a consequence of the reorder, and it is the point.** Only
three phases touch a frontend surface at all — 7, 9 and 10 — against seven in
the staged order, where the play-screen frame and the trace row contract had to
be frozen mid-stage and a shared seam assigned an owner because four phases
were editing the same files. Renderers now arrive with the events they render,
so nothing edits a dispatch point twice, and there is no freeze to enforce.

## 4. Scope fence

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
| **Hard-5 — integrating external data sources to enrich the agent's knowledge** | The SRD corpus and the authored content are the domain's knowledge, both shipped in-repo and pinned by version; fetching live data would make a save unreproducible |
| **Easy-5 — an interactive help chatbot** | The DM *is* the conversational surface; a second chatbot is redundant UI |
| **Easy-1 — asking ChatGPT to critique the solution** | Not a feature, so it cannot be a milestone; it is a review activity belonging to whoever prepares the submission |

## 5. Requirement and bonus mapping

### `135.md` task requirements

| # | Requirement | Banked by |
|---|---|---|
| 1 | Agent purpose, usefulness, target users | [app-vision.md](../../general/app-vision.md), restated in phase 11's documentation |
| 2 | Core functionality, primary tasks, user interactions | Phase 7 (the creation dialogue) and phase 8 (the turn, its tools and its interrupt) |
| 3 | A user-friendly UI for every functionality | Phases 7, 9 and 10 — read as stated in §7 below |
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

## 6. Open-decisions register

Recorded, not settled. Each is owned by a named phase and settled in that
phase's step spec — **the roadmap pins none of them**, and in particular
carries no concrete database schema. `phases.md` lists the same fifteen against
the same owners.

| Open decision | Owning phase |
|---|---|
| Where the cost figure comes from — a static price table in settings, or OpenRouter's usage-accounting field. **Trap: the static-table branch needs new declared settings that `.env.dist` has no entries for, and `.env.dist` is owner-only** | 2 |
| **The failure-injection seam** — how a provider failure is produced on demand: an unreachable base URL, a bogus model id, an injected timeout. A bad key is producible by editing `.env`; phase 8's timeout evidence and phase 7's image-failure evidence are not. Phase 2 defines one seam and both reuse it | 2 |
| Whether LangChain's OpenAI-compatible embeddings class can be pointed at the OpenRouter base URL, and so whether the seam's embedding side is a configuration of that class or a thin call of its own. Use `mcp__context7`; do not decide it from recall | 2 |
| **How the migration expresses the vector width — and only that.** `.env.dist` already pins the embedding model, states its native size, states that no `dimensions` parameter is ever sent, and requires a migration to change it. **Phase 4 must not pick a different model: `.env.dist` is owner-only** | 4 |
| **How** a fixture-local real engine is driven — not whether one is allowed, which `backend-stack.md` already permits. Doing it against async SQLAlchemy collides with the landed "fully synchronous suite, no `pytest-asyncio`, no async fixtures" rule, so this **may amend a landed decision**. Phase 5 inherits the answer | 4 |
| Ownership of a run: a membership row, or a user id on the run. **`model.md` and `architecture.md` currently rule for the membership row** — phase 5 may overturn that ruling, and §8 records the correction it must then make | 5 |
| The adventure's progress: its own entity, or fields on the run. **`model.md` currently rules for a separate entity** — same condition | 5 |
| The object state models and their read surface: their own module, or a service inside `playthrough` | 5 |
| The journal's retrieval policy — top-k plus the most recent N unconditionally, classification kept, weighted ranking dropped as unmeasurable against one adventure of data | 6 |
| The character capability: its own module, or a service inside `playthrough` | 7 |
| What triggers the deterministic portrait placeholder | 7 |
| The exact wording of the i18n carve-out: **agent-authored content — narration, citations, option labels, journal facts — is verbatim model output and is exempt from the i18n-key rule.** Owned here because the character sheet is the first model output rendered | 7 |
| The agent-progress milestone vocabulary, bound by the constraint that **nothing in the stream may reveal that a hidden roll happened**. Now one phase's own decision rather than a cross-phase constraint, because the stream and the rolls land together | 8 |
| The in-stream error representation. **Ruled: one error shape, two transports** — a turn failing after the 200 terminates the stream with an event carrying the same `{code, message, details}` object, so D4's single shape holds. Phase 8 pins the remaining transport detail | 8 |
| **What passes through the guard's override hook.** The free-text system-prompt override sits in the system position, upstream of everything a turn-inspecting guard reads, so this decides whether Medium-8's claim holds. **Phase 8 owns leaving the hook; phase 10 owns the policy, and the architect settles it, not the implementer** | 10 |

**Two items are pinned, not open**, and are recorded here so they are not
reopened: **character generation does not stream**, and **the interrupt's wire
shape and resume convention is pinned in phase 7 and reused verbatim in
phase 8**.

## 7. The requirement-3 reading

`135.md` requirement 3 asks for "a user-friendly interface for all
functionalities". Stage-01 reads that as **every *player* capability has a
surface** — and bottom-up ordering makes this reading carry more weight than it
did, so it is argued in full rather than asserted.

**Seven of eleven phases end without a screen: 1, 2, 3, 4, 5, 6 and 8.** They
fall into three kinds, and only the first is the familiar operator argument.

- **Operator capabilities** — SRD ingestion (4) and content validation (1).
  Run once by whoever deploys the system, never by a player. `135.md`'s own
  framing, "your user may not be that familiar with LLMs", is about the player,
  and giving these screens would put developer machinery inside the player
  experience — precisely what Medium-8 penalises. (Purge is not part of this
  argument: §4 fences it out of Stage-01, so there is no capability to
  justify.)
- **Internal plumbing** — the OpenRouter seam and prompt assets (2), dice (3).
  Nobody drives these directly at all; they are reached through a capability
  that does have a surface.
- **Headless backends** — runs and object state (5), journal memory (6), and
  the DM turn (8).
  These *are* player capabilities, and **this document does not claim
  otherwise.** They ship without a surface because the dependency graph puts
  the surface in a later phase, and the surface ships in that phase. The claim
  is that the capability has a surface **in Stage-01**, not in the phase that
  built it.

Every one of the seven names, in [phases.md](phases.md), **the demonstrable
that *is* its milestone** and **the later phase that surfaces it**: 1 → 7 and
8 · 2 → 8 and 10 · 3 → 8 and 9 · 4 → 9 · 5 → 7 · 6 → 9 · 8 → 9. Phase 11's
documentation makes the argument explicitly, so a reviewer meets it rather than
discovering a gap.

## 8. Doc-correction register

Contradictions between the existing `docs/general/` design and this plan.
Each is corrected by the phase that owns the change — not batched into
phase 11 — because a doc describing a capability the phase just changed is the
phase's own output. `phases.md` lists the same rows against the same owners.

| Contradiction | File | Owning phase |
|---|---|---|
| The content shape describes neither the per-adventure `intro` nor the seed player character | `general/model.md` | 1 |
| "Authored by an LLM once through a `generate_adventure` CLI that prompts with the SRD and enforces the schema" — content is hand-authored | `general/architecture.md` | 1 |
| Requirement 3's wording does not state the player-capability reading | `general/requirement-map.md` | 1 (states it) · 11 (full argument) |
| `docs/modules/` is empty and `docs/README.md` says "None yet" | `docs/README.md`, `docs/modules/` | every phase; first entry lands with 1 |
| The static-file tree lists a content-generation prompt asset that will not exist, **and pins the only prompt root as `game`'s directory** — which would place the character-generation prompt inside `game` even if the character capability becomes its own module, a module-boundary violation. The correction is the root convention: an id resolves against its owning capability's own prompt directory | `general/model.md` | 2 |
| "LangChain / LangGraph are declared but not wired yet" — they are not declared | `general/backend-stack.md` | 2 |
| D7's "exactly five settings" — **one amendment, not two**: the OpenRouter key, the chat, embedding and image models and the embedding dimension all become declared fields together, because all three call kinds land on one seam in one phase | `roadmap/phase-0/shared-knowledge.md` | 2 |
| The suite is "fully synchronous … no `pytest-asyncio` and no async fixtures", which a fixture-local async engine collides with. **A possibility, not a certainty**: if phase 4 needs one, it amends this landed decision rather than working around it | `general/backend-stack.md`, `roadmap/phase-0/shared-knowledge.md` | 4 |
| The combat paragraph, the encounter node in the entity diagram, "Encounter hangs off AdventureRun", and the encounter line in the lifecycle table | `general/model.md` | 5 |
| The **Encounter** run-term entry, and the **Initiative** game term, which now has no caller | `general/glossary.md` | 5 |
| Player-experience §3's "turn order beside the narration" | `general/app-vision.md` | 5 |
| The web-client bullet's "state panel (HP, AC, inventory, turn order)" | `general/architecture.md` | 5 |
| The lifecycle table's **Purge** row describes a capability §4 fences out of Stage-01 | `general/model.md` | 5 |
| **A confirmation, not a correction.** The lifecycle table's "generate the player's creature" on starting a playthrough is **correct as written** — phase 7 does exactly that, which is why character creation and the run are adjacent rather than swapped. Only the **seed character's fixture role** needs stating: it exists so phase 5 has a character before the generation agent lands | `general/model.md` | 5 |
| Nothing names a **seed player character**, so the fixture role above has no term | `general/glossary.md` | 5 |
| **Conditional, and it must be resolved either way.** "Ownership lives on the membership row" is written as a *ruling* in one file and repeated in the other, while §6 records it as an *open decision*. If phase 5 overturns it, phase 5 corrects both files; if phase 5 upholds it, phase 5 records that the decision is closed. **A phase-5 architect must not be left reading two documents that disagree about whether there is a choice** | `general/model.md`, `general/architecture.md` | 5 |
| **Conditional, same condition.** `AdventureRun` is written as a full entity with its own justification, while §6 records it as an open decision. Overturn and correct, or uphold and close | `general/model.md` | 5 |
| "Every user-facing string goes through a key; a literal in a component is a defect" needs the carve-out for **agent-authored content, which is verbatim model output** | `general/frontend-stack.md` | 7 |
| The tool table's `start_combat()` / `end_round()` rows | `general/architecture.md` | 8 |
| The wire convention describes only resource objects and one error envelope; SSE is a third response kind. **State affirmatively that D5 is not amended** — a long-lived SSE response is still one request, so "request-scoped or a CLI one-off" still holds | `general/architecture.md` | 8 |
| "`ask_player` **every turn**" — the DM asks when the decision is the player's, and one that asked every turn would not be narrating | `general/requirement-map.md` | 8 |
| The optional-task table: the corrected bonus slate; **Langfuse counted as insurance and scoped to chat-model calls only**; **Medium-2 banked by the checkpointer alone**, with the journal strengthening it; **Medium-8 requiring both halves**; and **Medium-3 considered and not claimed, with the reasoning** | `general/requirement-map.md` | 11 |
| "Current state: scaffolding … the game agent does not [exist]" | `general/architecture.md` | 11 |
