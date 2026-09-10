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
  **Milestone**: a finished, self-contained piece of functionality. A phase's
  completion *is* its milestone — there is no separate sign-off.
- A phase decomposes into **Steps**, each with its own step spec and its own
  phase directory. **Steps are not defined at this altitude and no phase
  directory exists yet**; both arrive when the phase is specced.
- This stage carries **no concrete database schema and no API structure**.
  Tables, columns, routes and payload shapes are pinned by step specs.

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

### Reasoning and LLM plumbing

| Capability | Placement | Why there | Phase |
|---|---|---|---|
| **LLM Gateway** — **the single OpenRouter seam**: the one place the credential lives and provider failures are classified, serving chat models *and* embeddings | `core/` singleton | The per-app-singleton carve-out, same class of object as the HTTP client and the DB engine; one seam means one credential site and one failure-classification site, so a second would be a second way to do the same thing. Phase 2 lands the chat side, phase 3 **extends the same seam** with the embedding side | 2, 3 |
| **Prompt Composer** — assembles the effective system prompt as base DM + personality + optional run override | Service inside `game` | One conceptual owner; other modules reach it through `game`'s service surface | 2 |
| **Prompt Assets** — the base DM prompt, the personality fragments, the character-generation prompt | Prompt asset files inside `game` | Prompts live in the module that uses them, versioned in git | 2, 8 |
| **Checkpointer Provisioning** — the LangGraph Postgres checkpointer's own setup, plus excluding its schema from Alembic | `core/` singleton + an Alembic configuration change | No job runner exists to call `setup()`, and a stray autogenerate would try to drop the schema; it is infrastructure, so it lands with the gateway rather than inside a feature phase | 2 |
| **Dungeon Master Agent** — the LangGraph loop and its tool registry | Services inside `game` | The tool layer is the module's public verb surface; each tool delegates to another module's service and contains no SQL | 5 |
| **Turn Transport** — the SSE stream carrying narration and agent-progress milestones | Service + route surface inside `game` | It is the turn's response, so it belongs to the turn's owner | 5 |
| **Turn Failure & Recovery** — a turn that dies mid-flight leaves state consistent, preserves the input and is retryable | Cross-cutting behaviour of the loop, inside `game` | It is a property of the loop, not a separate component | 5 |
| **Guard** — refuses prompt injection and out-of-band state claims | Service inside `game` | Single caller, wired as the node in front of the loop | 7 |
| **Character Generation Agent** — a described idea plus a follow-up or two becomes a sheet | **Open** — own module `character`, or a service inside `playthrough` | Undecidable at this altitude; see the open-decisions register | 8 |

### Content layer

| Capability | Placement | Why there | Phase |
|---|---|---|---|
| **Content Schema & Loader** — content models, version-pinned reads, load-time referential validation | Backend module `content` | A module is a domain, not a table: it owns models, schemas, a read surface and a service, and `playthrough` and `game` consume it through that service | 1 |
| **Authored Content Set** — one campaign, one adventure, ≥3 scenes, its NPCs and stat blocks, the pregen player character, and an authored prose `intro` per adventure | Content asset in git, mounted read-only | Not code; reviewed as a diff | 1 |
| **Content Validation CLI** | Typer one-off in `content` | Not a request, and D5 leaves the CLI as the only non-request seam | 1 |

### Knowledge layer

| Capability | Placement | Why there | Phase |
|---|---|---|---|
| **Embedding calls** — one pinned model, one dimension | The **embedding side of the LLM Gateway** in `core/`, from the start | Not a promotion-on-evidence case at all: it is the same provider, the same credential and the same failure classification as the chat side, so it is one seam extended rather than a new file to be moved later. `rules` and `journal` both call it | 3 |
| **SRD Rule Ingestion** — chunk and embed SRD 5.1 into pgvector | Typer CLI one-off in `rules` | One-time, not a request | 3 |
| **Rule Lookup** — similarity search returning passages with citable sections | Service inside `rules` | `game`'s `lookup_rule` tool calls it; tools contain no SQL | 3 |
| **Journal Memory** — agent-written durable canon, embedded on write, retrieved by similarity plus recency | Backend module `journal` | Own lifecycle (cascades with the run) and own retrieval policy; `game`'s journal tools call its service | 11 |

### Mechanics layer

| Capability | Placement | Why there | Phase |
|---|---|---|---|
| **Dice & Mechanics** — expression parse, RNG, visibility flag; deterministic, no LLM | A module of pure functions **inside `game`**, not `core/` | Exactly the promotion-on-evidence case: one caller at Stage-01. Promote unchanged if a second module ever rolls | 6 |
| **Playthrough Lifecycle** — start (pin campaign and content version, ownership, eager object instantiation), list, open, archive, unarchive, resume, and the per-run settings store | Backend module `playthrough` | Clear domain owner; settings live on the run, so the run owns them | 4 |
| **Initial scene placement** — which adventure is active, and the character starting in the entry scene | Service inside `playthrough` | Same aggregate and same transaction boundary; a second module for one child concern fails KISS | 4 |
| **Scene advance** — moving the character on an exit | With the validated write path, same owner | Position is object state, so advancing it is a validated write. Landing it in phase 4 would be a writer with nothing to write about — the same objection that moved Validated State Writes out of phase 4 | 6 |
| **Object State Models & Read Surface** — the per-kind state models and the sheet/state read path | **Open** — own module, or a service inside `playthrough` | Undecidable at this altitude; see the register | 4 |
| **Validated State Writes** — every write to an object's state validated against the model selected by kind | Same owner as the models above | Deliberately **not** in phase 4: a validator with no writer is speculative and untestable except through a synthetic caller | 6 |
| **Event Stream & Cost Accounting** — the append-only stream of narration, input, rolls, tool calls, errors and cost; visibility-filtered on read; run cost is a sum, never a column | Backend module `events` | Distinct lifecycle (append-only, never pruned) and two consumers — `game` writes, the trace and cost read paths read | 5 |
| **Portrait Media** — an OpenRouter image call, stored once to the media volume, served by a static route, with a deterministic placeholder | Service inside the character capability's owner, plus a static route and a Docker volume | Only caller | 8 |

### Frontend

| Capability | Placement | Why there | Phase |
|---|---|---|---|
| **App Shell & Navigation** | Promoted from `modules/home` to `src/components/` — **earned, not speculative** | At phase 4 it has two real module callers (`playthrough`, `game`); not before. The promotion holds **only if the shell keeps its `action?: ReactNode` slot pattern and imports from no module**, per D1's worked example — phase 4 adds navigation, which is exactly where sign-out and current-user creep in and disqualify it | 4 |
| **Playthrough Browser** — list, start, open, archive filter, unarchive | Frontend module `playthrough` | | 4 |
| **Play-screen frame, Narration pane, Composer, State pane, Trace pane** | Frontend module `game` | One screen, one module. The state pane is not its own module: it is one section with one caller | 4, 5 |
| **Term-explanation pattern** — a game term explained where it appears | A component inside `game` | One module caller at Stage-01; promoted to `components/` only if a second module renders it | 4 |
| **Failure / refusal pattern** | A component inside `game` | Same reasoning | 5 |
| **Character Creation screen** | Frontend module `character` | Mirrors its backend owner | 8 |
| **Journal view** — a read-only pane reachable from the play screen | A component **inside `game`**, with its own hook | One read-only pane plus one hook, rendered by `game`'s play screen. "Mirrors the backend module" is not the bar this document uses — it refuses the state pane a module of its own on exactly those grounds. Backend `journal` stays a module: it has its own table and its own lifecycle | 11 |
| **Developer Drawer** — model, temperature, personality, one marked free-text prompt override, plus the composed prompt and pinned content version read-only | Frontend module `devtools` | **Not the same case as the journal view.** Medium-8 grades the developer/player separation *structurally*, so a separate module makes the fence a fact about the tree rather than a convention; the journal view has no such requirement behind it | 9 |

### Release

| Capability | Placement | Why there | Phase |
|---|---|---|---|
| **Observability** — Langfuse tracing on every **chat-model** call | `core/` wiring on the gateway | One callback attached where the chat model is built; no new module. **Embedding calls are never traced** — LangChain's embeddings class emits no callback events, as `.env.dist` already states — so phases 3 and 11's embedding calls are outside the trace by nature, not by omission | 12 |
| **Release Documentation** — usage, worked examples, the tool reference, the content authoring guide, decision records | `docs/modules/*.md` plus each module's `README.md` | Per-phase obligation, not a deferred batch: each module states its own intent, surface and quirks | every phase; completed 12 |

## 2. Dependency graph

**Build dependency** — cannot land or pass its own tests without it.
**Demo dependency** — lands and passes tests, but a reviewer cannot see the
point until the other exists.

### Build dependencies

```
LLM Gateway, chat side  ──> Prompt Composer, DM Agent,
                            Character Generation, Guard, Observability
LLM Gateway, embedding side ──> SRD Ingestion ──> Rule Lookup ──> lookup_rule
                            ──> Journal Memory ──> the journal tools

Content Schema & Loader ──> Authored Content Set (it validates it),
                            Playthrough Lifecycle (pin + eager instantiation),
                            Initial scene placement,
                            DM Agent's get_scene / get_monster

Playthrough Lifecycle ──> Object State, Initial scene placement, Event Stream,
                          Journal Memory, the run-settings write surface

Object State ──> State pane (read)
Object State ──> Validated State Writes ──> update_object, Scene advance
Event Stream ──> Trace pane, Cost Accounting, Turn Failure & Recovery
DM Agent ──> Event Stream (every turn writes events), Turn Transport
Dice ──> roll_dice
App Shell ──> Playthrough Browser, Play-screen frame, Developer Drawer
```

### The load-bearing distinctions

- **`lookup_rule` and the journal tools are tool *additions*.** The loop
  compiles, runs and demonstrates without them, so they are not build
  dependencies of the agent — the direction is reversed, they depend on the
  agent's tool registry. This is what makes the back half parallelisable.
- **The Guard is not a build dependency of the agent** either; it is a node
  inserted in front. It is still scheduled before the bonus group, because an
  unguarded free-text-into-tool-calling loop is a shippable vulnerability.
- **The Developer Drawer is buildable after phase 4 and demonstrable only
  after phase 5** — temperature and personality have nothing to affect until a
  model narrates. The cleanest build-vs-demo split in the stage.
- **The Trace pane is buildable with the Event Stream and demonstrable only
  once a turn produces events.**
- **The Authored Content Set is a demo dependency of the DM Agent** and a
  build dependency of nothing: the loader validates a schema, not a campaign.
- **Character generation depends on the agent loop and the interrupt, not the
  reverse.** Nothing in the loop needs it.
- **Phase 6 before phase 7 is a build recommendation, but phase 6 is a *demo*
  dependency of phase 7.** Interrupts and the guard attach to the graph and the
  stream; neither reads a die roll or an object patch, so the build dependency
  is phase 5 alone. But phase 7's "refused with **no state change**" criterion
  is vacuous until phase 6 exists, because before it there is no state a turn
  could have changed. They may be parallelised **only** if the shared seam has
  a single owner (see group C), and phase 7's no-state-change evidence is only
  meaningful once 6 has landed.
- **Phases 5 and 6 knowingly ship a free-text-into-tool-calling loop with no
  guard.** The guard arrives in phase 7, so for two phases the mitigation is
  *scheduling* and nothing else. Stated plainly rather than left implied: the
  input cap in phase 5 is the only control in place, these phases are not a
  deployable state, and phase 7 is not droppable.

## 3. Phases

| # | Phase | Milestone (shipped functionality) | Deps | Parallel with |
|---|---|---|---|---|
| 1 | Content foundation | One campaign, one adventure, ≥3 scenes, a pregen player character and an authored prose intro per adventure, as validated JSON loadable at a pinned version and **present and readable in the content read surface** | 0 | 2 |
| 2 | LLM gateway & prompt assets | The app talks to a model through OpenRouter via LangChain; the DM's effective prompt is a composed, inspectable artefact; the checkpointer's schema is provisioned and excluded from Alembic | 0 | 1 |
| 3 | SRD knowledge base | SRD 5.1 ingested into pgvector; a rules question returns relevant passages with citable sections | 2 | 4 |
| 4 | Playthrough & character state | A player starts a run of the shipped campaign, sees it listed, opens it, reads the adventure intro, inspects a sheet with its terms explained, archives and unarchives it, reloads and resumes | 1 | 3 |
| 5 | The DM turn loop | Plain words in, streamed narration out with progress milestones; the DM reads scene facts and stat blocks through `get_scene` / `get_monster`; the turn is recorded as events with its cost; history survives a reload; a failed turn is recoverable and does not eat the input | 1, 2, 4 | — |
| 6 | Real dice, real consequences | Actions resolve on visibility-aware dice against real target numbers; consequences land in validated state and the player watches HP change; the character advances between scenes on an exit; the outcome of a hidden roll changes the narration and no roll row appears for it | 5 | — (7 recommended after) |
| 7 | Human-in-the-loop & the guard | The DM asks when the decision is the player's, the interrupt survives a reload, and injection and out-of-band state claims are refused legibly | 5 | 6, with a single seam owner |
| 8 | Character creation in plain words | A described idea plus a follow-up or two becomes a finished sheet with a portrait; phase 4's pregen becomes an explicit quick-start | 2, 4, 5, 7 | 9, 10, 11 |
| 9 | Developer drawer | Model, temperature, personality and one marked prompt override are changeable per run outside the player experience, with the composed prompt and pinned content version shown read-only; a change is carried into the next turn, observable in the composed prompt and the trace's model id and cost line | 4, 5 | 8, 10, 11 |
| 10 | Agentic rule lookup | The DM decides for itself when it needs a rule, may re-query, and the player sees the SRD section cited | 3, 5 | 8, 9, 11 |
| 11 | Journal memory | The DM writes down what becomes true and recalls it later, including what the player invented; retrieval is visible and a read-only journal view is reachable from the play screen | 3, 5 | 8, 9, 10 |
| 12 | Release: observability & documentation | Every **chat-model** call is traceable in Langfuse when enabled; the docs let a stranger run and understand the agent, with worked examples and decision records | Langfuse half: 2 · documentation half: 11 **and whatever of group C lands** | — |

### Parallel groups

- **Group A = {1, 2}** — disjoint trees, disjoint assets. Content is
  hand-authored, so phase 1 needs no model.
- **Group B = {3, 4}** — disjoint modules, but **not disjoint Alembic
  revisions**: both would stack a revision on the same `down_revision` and both
  add a line to `alembic/env.py`. The revision chain is linear, so the two
  phases are assigned an explicit revision order and the later one rebases onto
  the earlier one's head. The hazard is the *heads*, not the migration content.
- **Group C = {8, 9, 10, 11}** — four additions on a frame whose *contract* is
  frozen at the end of phase 7. **The freeze pins the contract and assigns no
  file ownership, and these four phases are not file-disjoint:** all of them
  edit `frontend/src/modules/game` — the portrait in the state pane (8), the
  drawer entry point (9), a trace renderer each (10, 11) and the journal entry
  point (11) — and the trace-renderer dispatch point is one file that two of
  them edit. **The seam is therefore the tool registry, the trace-renderer
  dispatch point and the play-screen frame's entry points**, and those files
  have a **single owner for the duration of group C**, or group C's members
  land into them **sequentially**. Phase 11 also repeats group B's revision-head
  hazard and takes its place in the same explicit revision order.
- **Group C's parallelism is additionally conditional on a decision phase 8 has
  not made.** If phase 8's placement decision resolves to a service inside
  `playthrough` rather than its own module, phases 8 and 9 both write into
  backend `playthrough` — 8 for generation, 9 for the run-settings write
  surface — and the claim of independence no longer holds for that pair.
- **Priority inside group C: 8 and 10.** 8 pays requirements 2 and 3, 10 banks
  Hard-1. **This is not licence to drop 9**: Medium-8 requires the guard *and*
  the developer/player split, so without phase 9 the guard in phase 7 banks
  nothing.
- Phases 5, 6, 7 and 12 run alone.

**Longest chain of build dependencies:** 1 → 4 → 5 → 7 → 8 → 12. Phase 6 is
not on it — §2 records it as a *demo* dependency of phase 7, not a build one —
so the practical order is 1 → 4 → 5 → 6 → 7 → 8 → 12. Phase 12's documentation
half additionally waits on whatever of group C lands, because it cannot
document character creation, the drawer or the rule tool before they exist.

### Why phase 5 is one phase and not three

The SSE transport, the graph loop, the event stream and the trace pane are one
seam: a loop without the stream is a transport that gets thrown away, an event
stream without the loop is CLI-only, and a trace pane without events renders
nothing. Every candidate split produces either discarded work or a milestone
nobody can see. The de-risking happened instead by moving dice to phase 6,
interrupts and the guard to phase 7, and the checkpointer's provisioning back
to phase 2.

## 4. Scope fence

| Out of Stage-01 | Reason |
|---|---|
| **Combat as a simulated system** — no encounter entity, no initiative order, no round or turn tracking, no turn-order pane | Game design, not agent knowledge: a fight resolves with dice and consequences, and nothing in `135.md` grades initiative |
| **The LLM content-generation CLI** and its prompt asset | Content is hand-authored for Stage-01, so the generator has no caller; the content-version machinery already admits more content later |
| **Turn cancellation** | Retry on a *failed* turn covers the real need; a mid-stream abort is a second control path with no graded requirement behind it |
| **Retrying a completed turn** | A finished turn is canon — re-rolling it would make the dice negotiable |
| **A timed undo on archive** | Archive is reversible by an explicit unarchive with a confirm, which is simpler and has no timer to get wrong |
| **Portrait-only reroll, and unbounded character regeneration** | One reject-and-re-derive before acceptance is enough to feel in control; more turns a creation flow into a slot machine |
| **Purge (hard deletion of archived runs)** | An operator convenience; archive is the player-facing gesture and nothing in `135.md` needs hard deletion |
| **`app sessions prune`** (phase-0 known future work) | Expired sessions are already treated as absent; unbounded row growth is not a graded concern |
| **Multiplayer, maps, voice** | The vision places them in a later capstone |
| **A second adventure or campaign** | One is the stated initial content set, and a new content version adds more without a migration |
| **User-level settings or an override chain** | Settings live on the run; a second layer has no caller |
| **Medium-5 / Hard-4 — feedback loops and learning from feedback** | The bonus slate is already met with insurance |
| **Medium-6 — plugin system and player-toggleable tools** | Same, and a DM whose dice tool can be switched off stops being trustworthy |
| **Medium-7 — multi-model support beyond OpenRouter model selection** | Model choice through one gateway already covers the intent; a second provider adds a credential and no evidence |
| **Hard-3 — a Ragas / DeepEval evaluation report** | Same, and it measures quality this stage has no baseline for |
| **Hard-5 — integrating external data sources to enrich the agent's knowledge** | The SRD corpus and the authored content are the domain's knowledge, both shipped in-repo and pinned by version; fetching live data would make a save unreproducible |
| **Easy-5 — an interactive help chatbot** | The DM *is* the conversational surface; a second chatbot is redundant UI |
| **Easy-1 — asking ChatGPT to critique the solution** | Not a feature, so it cannot be a milestone; it is a review activity that belongs to whoever prepares the submission |

## 5. Requirement and bonus mapping

### `135.md` task requirements

| # | Requirement | Banked by |
|---|---|---|
| 1 | Agent purpose, usefulness, target users | [app-vision.md](../../general/app-vision.md), restated in phase 12's documentation |
| 2 | Core functionality, primary tasks, user interactions | Phases 5, 6, 7 (the loop, real mechanics, the interrupt) and 8 (the creation dialogue) |
| 3 | A user-friendly UI for every functionality | Phases 4, 5, 6, 7, 8, 9, 11 — read as stated in §7 below |
| 4 | Appropriate tools, error handling, real-world usage | Phases 2 (model failures), 5 (turn failure and recovery), 6 (invalid expressions, rejected writes), 7 (refusals), 10 (empty retrieval) |
| 5 | Documentation: usage, examples, technical decisions | Every phase's module doc; completed and proven by phase 12's fresh-checkout run-through |

### Optional tasks targeted

| Brief task | Mechanic | Banked by |
|---|---|---|
| **Medium-1** — token usage and cost | Summed from the event stream; per turn on the trace row, run total in the play-screen header and on the list row | Phase 5 |
| **Medium-2** — long **or** short-term memory | The checkpointer (short) · journal entries with similarity-plus-recency retrieval (long) | **Phase 5 banks it alone** — the brief says "long-term *or* short-term", so the checkpointer satisfies it. **Phase 11 strengthens it rather than completing it** |
| **Medium-8** — a security guard, **and** developer settings kept out of the player experience | The guard node · the developer drawer | Phases 7 **and** 9 together. The brief conjoins the two, so **neither phase banks it alone and phase 9 is not droppable** |
| **Hard-1** — agentic RAG | The DM decides whether to look a rule up and may re-query | Phase 3 (corpus) + **phase 10** (the tool) |
| **Hard-2** — LLM observability | Langfuse tracing of every **chat-model** call, counted as **insurance** rather than as the primary hard task | Phase 12 |
| Easy-2 — personality | DM tone per run | Phase 2 (assets) + phase 9 (selection) |
| Easy-3 / Easy-4 — model choice and settings | Model and temperature in the drawer | Phase 9 |
| Medium-4 — authentication and personalisation | Landed auth plus per-run settings | Phase 0 + phase 4 |

**Medium-3 — an extra function tool calling an external API — is considered
and not claimed.** The portrait call is a one-shot step inside character
generation rather than a tool in an agent's registry, and it reaches the same
OpenRouter credential the model already uses, so both halves of the claim
would be a stretch. The slate above already exceeds ≥2 medium + 1 hard.
Phase 12 records the reasoning in
[requirement-map.md](../../general/requirement-map.md), because a reviewer who
sees the judgement scores it better than one who sees an overreach.

## 6. Open-decisions register

Recorded, not settled. Each is owned by a named phase and is settled in that
phase's step spec — **the roadmap pins none of them**, and in particular
carries no concrete database schema.

| Open decision | Owning phase |
|---|---|
| Where the cost figure comes from — a static price table in settings, or OpenRouter's usage-accounting field. **Trap: the static-table branch needs new declared settings that `.env.dist` has no entries for, and `.env.dist` is owner-only** — that branch cannot be taken without an owner edit | 2 |
| **The failure-injection seam** — how a provider failure is produced on demand: an unreachable base URL, a bogus model id, an injected timeout. A bad key is producible by editing `.env`; a **timeout** (phase 5's evidence) and an **image failure** (phase 8's) are not, and the drawer that could stand in arrives after two of the three. Phase 2 defines one seam; **phases 5 and 8 reuse it rather than each inventing one** | 2 |
| Whether LangChain's OpenAI-compatible embeddings class can simply be pointed at the OpenRouter base URL — the embedding side of the single seam. Use `mcp__context7` when phase 3 is specced; do not decide it from recall | 3 |
| **How the migration expresses the vector width** — and only that. `.env.dist` already pins `EMBEDDING_MODEL`, states that its native size is 1536 and that no `dimensions` parameter is ever sent, and requires a migration to change it. **Phase 3 must not pick a different embedding model: `.env.dist` is owner-only** | 3 |
| **How** a fixture-local real engine is driven, not whether one is allowed — `backend-stack.md` already permits it. The narrower problem is that doing it against async SQLAlchemy collides with the landed "no `pytest-asyncio`, no async fixtures, the suite is fully synchronous" rule, so **phase 3 may have to amend a landed decision** rather than merely make one. Similarity search is inherently database-bound, so this phase forces the answer | 3 |
| Ownership of a run: a membership row, or a user id on the run. **`model.md` and `architecture.md` currently rule for the membership row** — phase 4 may overturn that ruling, and §8 records the correction it must then make | 4 |
| The adventure's progress: its own entity, or fields on the run. **`model.md` currently rules for a separate entity** — same condition | 4 |
| The object state models and read surface: their own module, or a service inside `playthrough` | 4 |
| The agent-progress milestone vocabulary — bound in advance by phase 6's constraint that nothing may reveal a hidden roll happened | 5 |
| The in-stream error representation. **Ruled: one error shape, two transports** — a turn failing after the 200 terminates the stream with an event carrying the same `{code, message, details}` object, so D4's single shape holds. Phase 5 pins the remaining transport detail | 5 |
| The residual i18n wording. **Ruled: agent-authored content — narration, citations, option labels, journal facts — is verbatim model output and is exempt from the i18n-key rule.** Open only in how `general/frontend-stack.md` expresses it | 5 |
| Character generation: its own module, or a service inside `playthrough` | 8 |
| What triggers the deterministic portrait placeholder | 8 |
| **What the guard does about the free-text system-prompt override.** The override sits in the system position, upstream of everything a turn-inspecting guard looks at, so this decides whether Medium-8's claim holds at the phase meant to bank it. **The architect settles this, not the implementer** | 9 |
| The journal's retrieval policy — top-k plus the most recent N unconditionally, classification kept, weighted ranking dropped | 11 |

## 7. The requirement-3 reading

`135.md` requirement 3 asks for "a user-friendly interface for all
functionalities". Stage-01 reads that as **every *player* capability has a
surface**.

SRD ingestion and content validation are **operator** capabilities: they are
run once by whoever deploys the system, never by a player, and `135.md`'s own
framing — "your user may not be that familiar with LLMs" — is about the player.
Giving them screens would put developer machinery inside the player experience,
which is precisely what Medium-8 penalises. They stay CLI-only, and phase 12's
documentation makes the argument explicitly so a reviewer meets it rather than
discovering a gap. (Purge is not part of this argument: §4 fences it out of
Stage-01 entirely, so there is no capability to justify.)

Phases 1, 2 and 3 therefore ship no screen — but **for two different reasons,
and phase 2 is not part of the argument above.** Phases 1 and 3 ship operator
capabilities. Phase 2 ships **internal plumbing**: the gateway and the prompt
composer are not a capability anyone drives directly, and they are surfaced to
the player by phase 5 (the prompt drives the narration) and phase 9 (the drawer
shows the composed prompt read-only). Each of the three names, in
[phases.md](phases.md), the human-readable CLI demonstrable that *is* its
milestone and the later phase that surfaces it.

## 8. Doc-correction register

Contradictions between the existing `docs/general/` design and this plan.
Each is corrected by the phase that owns the change — not batched into
phase 12 — because a doc that describes a capability the phase just changed is
the phase's own output.

| Contradiction | File | Owning phase |
|---|---|---|
| Neither the `intro` field per adventure nor the pregen player character is described in the content shape | `general/model.md` | 1 |
| "Authored by an LLM once through a `generate_adventure` CLI that prompts with the SRD and enforces the schema" — content is hand-authored | `general/architecture.md` | 1 |
| Requirement 3's wording does not state the player-capability reading | `general/requirement-map.md` | 1 (states it) · 12 (full argument) |
| `docs/modules/` is empty and `docs/README.md` says "None yet" | `docs/README.md`, `docs/modules/` | every phase; first entry lands with 1 |
| The suite is "fully synchronous … no `pytest-asyncio` and no async fixtures", which a fixture-local async engine collides with. **Possibility, not a certainty**: if phase 3 needs one, it amends this landed decision rather than working around it | `general/backend-stack.md`, `roadmap/phase-0/shared-knowledge.md` | 3 |
| The static-file tree lists a content-generation prompt asset that will not exist | `general/model.md` | 2 |
| "LangChain / LangGraph are declared but not wired yet" — they are not declared | `general/backend-stack.md` | 2 |
| D7's "exactly five settings" — **first amendment**: the OpenRouter key, chat model, embedding model and embedding dimensions become declared fields | `roadmap/phase-0/shared-knowledge.md` | 2 |
| The lifecycle table's **Purge** row describes a capability §4 fences out of Stage-01. Owned here because phase 4 already owns the rest of that table's edits | `general/model.md` | 4 |
| The lifecycle table's "generate the player's creature" on starting a playthrough — phase 1's **pregen** does it, and phase 8's generation agent replaces the pregen | `general/model.md` | 4 |
| A **pregen player character** has no term, so nothing names the thing phase 8 turns into a quick-start | `general/glossary.md` | 4 |
| **Conditional, and it must be resolved either way.** "Ownership lives on the membership row" is written as a *ruling*, while §6 records it as an *open decision*. If phase 4 overturns it, phase 4 corrects both files; if phase 4 upholds it, phase 4 records that the decision is closed. **A phase-4 architect must not be left reading two documents that disagree about whether there is a choice** | `general/model.md`, `general/architecture.md` | 4 |
| **Conditional, same condition.** `AdventureRun` is written as a full entity with its own justification, while §6 records it as an open decision. Overturn and correct, or uphold and close | `general/model.md` | 4 |
| The combat paragraph, the encounter node in the entity diagram, "Encounter hangs off AdventureRun", and the encounter line in the lifecycle table | `general/model.md` | 4 |
| The **Encounter** run-term entry, and the **Initiative** game term, which now has no caller | `general/glossary.md` | 4 |
| Player-experience §3's "turn order beside the narration" | `general/app-vision.md` | 4 |
| The web-client bullet's "state panel (HP, AC, inventory, turn order)" | `general/architecture.md` | 4 |
| The tool table's `start_combat()` / `end_round()` rows | `general/architecture.md` | 5 |
| The wire convention describes only resource objects and one error envelope; SSE is a third response kind. **State affirmatively that D5 is not amended** — a long-lived SSE response is still one request, so "request-scoped or a CLI one-off" still holds | `general/architecture.md` | 5 |
| "Every user-facing string goes through a key; a literal in a component is a defect" needs the carve-out for **agent-authored content — narration, citations, option labels, journal facts — which is verbatim model output** | `general/frontend-stack.md` | 5 |
| "`ask_player` **every turn**" — the DM asks when the decision is the player's, not on every turn, and a DM that asked every turn would not be narrating | `general/requirement-map.md` | 7 |
| D7 — **second amendment**: the image model becomes a declared field. Recorded here so the second amendment does not read as a contradiction of the first | `roadmap/phase-0/shared-knowledge.md` | 8 |
| The optional-task table: the corrected bonus slate, **Langfuse counted as insurance and scoped to chat-model calls only** (embeddings emit no callback events), Medium-2 banked by the checkpointer alone, Medium-8 requiring both halves, and Medium-3 considered and not claimed | `general/requirement-map.md` | 12 |
| "Current state: scaffolding … the game agent does not [exist]" | `general/architecture.md` | 12 |
