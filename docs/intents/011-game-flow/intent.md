---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-23
updated: 2026-09-24
stage: approved
---
# Game Flow

Implement the game flow described in
[`docs/general/game-flow.v2.md`](../../general/game-flow.v2.md) as one small,
durable LangGraph workflow.

This is a full refactor of the game logic. Existing code may be reused where it
fits the target design, but compatibility with the current internal graph,
tools, state, and tests is not a goal. Remove superseded code and tests as part
of the same change.

## Outcome

One graph runs an opening and every later player turn through five nodes:

```text
START -> advance -> decide       -> advance
                 -> execute      -> advance
                 -> await_player -> advance
                 -> narrate      -> advance
                 -> END
```

`advance` is the only scheduler and router. It selects one next effect from
checkpointed workflow state and freshly loaded world facts. The other four
nodes perform that effect and return control to `advance`. Deterministic
services own every roll and state change. Models may choose or describe
outcomes, but cannot invent rolls or edit state.

## Current implementation audit

### Reuse

- Keep the playthrough event stream as the public transcript and audit trail.
- Keep the campaign, adventure, member, object, and event domain models.
- Reuse the dice parser and actor, item, creature, and attack-derived formulas
  after the corrections below.
- Reuse campaign-content, rules-retrieval, and transcript-history read services
  behind the new projection and operation boundaries.
- Preserve the turn endpoint's text input and `awaiting` response unless the
  implementation demonstrates that a wire change is necessary.
- Retain useful route, authentication, transcript, and playthrough service
  tests.

### Change

| Current implementation | Required change |
| --- | --- |
| `DmState(MessagesState)` uses an ever-growing provider conversation as workflow state | Replace it with explicit turn, move, cursor, request, effect, result, usage, and error fields. Load the situation per call and construct temporary model messages from world state, the current turn, recent transcript events, and recalled older narration. |
| The graph has many nodes and combat-specific routes | Use only `advance`, `decide`, `execute`, `await_player`, and `narrate`, with one router after `advance`. |
| `narrate` is bound to LangChain tools and loops through `ToolNode` | Make narration tool-free. Select operations in `decide` and run deterministic handlers in `execute`. |
| Graph nodes query SQL and build a partial text context | Add an authoritative playthrough situation projection and pass structured data to prompts. Do not suppress projection errors. |
| Player requests are inferred from transcript events and checkpoint messages | Store the active request explicitly in graph state. Completed request and response events remain history for display. |
| Services scan JSON payloads to find spent rolls, damaged hits, and actors that acted | Track those obligations in the active action and combat cursors. Events remain history rather than workflow state. |
| Roll resolution can sample a new roll on retry | Keep the roll result and its consumer in graph state for the active action. Accept the narrow commit-before-checkpoint replay risk. |
| `attack` returns text and the graph searches the latest event for a hit ID | Return a typed result containing the hit ID. |
| Critical hits use the normal damage formula | Double the attack's damage dice and apply flat modifiers once. |
| A downed hero can still appear alive | Make down state and actor eligibility consistent in mutation and projection. |
| Initiative combines a player request, hostile rolls, and settlement | Use one hero-side roll and one hostile-side roll, then settle a stable side and actor order once per fight. |
| Fixture interaction records prose without changing fixture state | Persist successful fixture outcomes in playthrough object state. |
| Exit use lacks turn identity and a useful return value | Accept the turn ID and return a typed result. |
| The game module appends and commits question answers | Move persistence and transaction boundaries into playthrough service functions. |
| Expected mechanic failures raise generic exceptions | Return typed `refused` results. Reserve exceptions for ownership, identity, lifecycle, and infrastructure errors. |
| Monster flow selects the first non-member and ignores disposition, attacks, and other actors | Derive eligibility from the situation and run every eligible hostile through the combat cursor. |
| Actor roles are inferred ad hoc | Derive roles from membership, actor kind, disposition, and capabilities. Do not add a duplicate role column. |

### Missing

- Explicit checkpoint state for the current operation, result and player
  request.
- Cursor ownership of rolls, hits and per-round actions while they are active.
- A complete situation projection containing visible and hidden facts, fixtures,
  exits and conditions, object state, creature disposition and attacks, actor
  status, and relevant runtime state.
- Typed effects and operation results.
- Decision validation against allowed decision kinds and references.
- One operation registry shared by validation and execution.
- Explicit action, combat and narration cursors, a pending-hit obligation, and
  a simple reaction queue.
- A deterministic scheduler with a documented priority order.
- Evidence references that restrict narration to recorded facts and results.
- End-to-end checkpoint coverage across interrupts and multiple combat turns.

### Remove

- The LangChain `@tool` collection and `ToolNode` loop, except the two
  read-only knowledge tools rebound inside `decide`.
- `MessagesState` as durable game state and message-scanning helpers for
  answers, rolls, hits, and open turns.
- The regex guard node and the prompt instructions used to police the tool loop.
- Separate player-hit, monster-turn, monster-attack, and monster-damage nodes.
- `_already_acted` and payload scans that duplicate active cursor state.
- The always-refusing `use_item` operation until item use has authored rules.
- Generic custom dice as a gameplay operation. Retain only an internal dice
  primitive used by deterministic services.
- Tests that assert obsolete nodes, edges, tool schemas, or prompt wording.
- Generated `backend/graph.png` and other artifacts for the old topology.

## Persistence boundary

LangGraph checkpoints are the only persistence for orchestration state: the
current turn and move, requests and responses, operation results, action order,
combat order, reactions, pending hit, narration progress, and next effect.

The database persists only lasting game facts and history:

- objects store positions, ownership, stats and other durable world state;
- run records store lifecycle;
- events store player-visible and diagnostic history for redisplay and recall.

Do not add operation or pending-request tables, event-consumption columns, or a
workflow migration. Clear turn-only request, action, result and narration state
when the turn closes. Keep `CombatCursor` across player turns while combat is
active, then clear it when combat ends. Events already preserve the historical
outcome.

Player requests keep their two-row transcript form. The **request_roll** and
**request_choice** operations append the player-visible `roll_requested` or
`question` event before the graph pauses, and **roll_player** or
**accept_choice** appends the answering `roll` or `player_action` event after
it. Rows are never updated. The graph checkpoint decides control flow, while
the events endpoint keeps deriving `awaiting` from an unanswered request row in
the open turn, so the two can never disagree. The events read may add a derived
per-request status, open or done with the answering event ID, for the UI.

Operation and request IDs still correlate effects with results inside graph
state, but they are not database identities. Accept the narrow failure window
where a service commits and the following checkpoint fails; a retry may repeat
that mutation or roll. Execute operations serially and do not automatically
retry mutating operations. Add event-level deduplication later only if real use
shows this failure matters.

## Implementation plan

Implement in this order. Steps 1 and 2 establish the deterministic playthrough
foundation. Steps 3 through 8 build the state, handlers and node functions.
Compose the graph only in step 9.

### 1. Align deterministic playthrough services

Start with the functions that own rolls and lasting state changes.

1. Add structured ability or skill fields to secret and fixture checks, and
   update Greenhollow content. Runtime code must not parse mechanics from prose.
2. Retain one internal dice primitive and correct formula derivation. Implement
   automatic actor rolls, passive checks, active checks and saving throws.
3. Provide derived initiative rolls and deterministic side settlement. The
   graph will request one hero-side roll and make one automatic hostile-side
   roll. The hero side wins a tie, and initiative is established once per
   fight.
4. Make attack resolution return a typed hit, miss or critical result with its
   hit ID. Make damage apply the current plan's hit and damage roll in one
   transaction. Double critical damage dice and apply flat modifiers once.
5. Make HP, alive and down state agree in mutations and reads.
6. Align fixture interaction, take, drop, give, exit use, scene entry,
   hostility changes and scene departure. Successful durable fixture changes
   belong in object state.
7. Add explicit run completion for victory, defeat and authored completion.
8. Add playthrough-owned functions for recording player actions, answers,
   mechanic outcomes and narration. The game module must not commit.
9. Remove monolithic initiative, event scans for spent rolls, hits and acted
   creatures, and the always-refusing item-use implementation.

Every mutating service returns a typed result with status, public facts and the
IDs needed by the active graph. Expected mechanic refusals return a refused
result. Ownership, identity, lifecycle and infrastructure failures remain
errors.

Minimal tests:

- derived active, passive, save and initiative rolls;
- normal, missed and critical attacks through damage and down state;
- fixture, inventory and scene mutations;
- run completion and event recording.

### 2. Build the situation and memory reads

1. Implement **playthrough.service.get_situation** as the graph's authoritative
   read of the current run, adventure, scene, actors, membership-derived roles,
   HP and down state, disposition, attacks, inventory, fixtures, exits,
   conditions, authored facts and consequences.
2. Split its output into private decision evidence and public narration
   evidence. Hidden facts, DCs and private intent must not enter narration.
3. Include a bounded recent transcript window.
4. Extend history recall by using semantic narration matches as anchors and
   returning surrounding player-visible events with the same turn ID.
5. Raise projection errors rather than returning partial context.
6. Build the projection when **advance**, **decide** or **narrate** needs it.
   Never checkpoint it or a full provider-message history.

Minimal tests:

- one rich scene contains every field needed by decisions and combat;
- the public projection excludes hidden mechanics;
- an older fact outside the recent window reaches the requesting decision.

### 3. Define effects and checkpoint state

Use **TypedDict**, dataclasses, enums, literals and unions for internal graph
types. Use Pydantic only for an existing serialization or validation boundary,
or when the chosen structured-output adapter requires it.

Define:

- **TurnFrame** for run, turn, actor and opening, action or resume input;
- **Move** for normalized intent and validated references;
- **ActionCursor** for one actor's plan and current step;
- **CombatCursor** for scene, side order, stable actor IDs, current index, round
  and round admission;
- **AwaitingRef** for one checkpointed roll or choice request and its private
  consumer binding;
- **pending_hit_id** for the unresolved damage obligation;
- **reactions** as an ordered list of pending reaction specifications;
- **NarrativeCursor** for pending beat request or draft;
- **NextEffect** and matching decision, operation, resume and beat results;
- model usage and a structured execution error.

The checkpoint is authoritative only while work is active. Clear turn-local
request, response, action, operation result, reaction and narration fields when
the turn closes. Keep the combat cursor across player turns while the fight is
active and clear it when combat ends. Do not add workflow tables or a migration.

Operation and request IDs correlate checkpointed effects and results only.
Execute mutations serially and do not retry them automatically. Accept the
documented commit-before-checkpoint replay risk.

Minimal test: serialize and restore an interrupted request and an active combat
cursor, then prove turn and combat closure clear the correct fields.

### 4. Implement the operation handlers

Replace model-facing LangChain tools with one typed handler registry. Each
handler performs one operation and either updates checkpoint state or calls a
public domain service. Handlers contain no transaction control or direct access
to another module's internals.

Required handlers:

- lifecycle: **record_beat**, **complete_action**, **close_turn** and
  **finish_run**;
- player input: **request_roll**, **roll_player**, **request_choice**,
  **accept_choice**;
- checks: **roll_actor**, **passive_check**, **resolve_check**,
  **resolve_save**, **settle_initiative**;
- world: **interact**, **take_item**, **drop_item**, **give_item**,
  **use_exit**, **enter_next_adventure**, **set_hostility** and
  **leave_scene**;
- combat: **resolve_attack** and **apply_damage**.

Validate actor, attack, item, fixture, exit and choice references against the
fresh situation before dispatch. The client and model never supply a die result,
arbitrary continuation or state patch.

Minimal tests:

- every operation kind has one handler;
- invalid or stale references reach no mutation service;
- one representative handler dispatches and returns its typed result;
- one graph action cannot apply its active roll twice in normal flow.

### 5. Implement decision strategies and narration

Use one **decide** node with focused strategies for:

- reading a player move;
- interpreting rules or recalled evidence;
- judging ambiguous references;
- assessing authored checks, exits, fixtures and consequences;
- choosing a monster action;
- choosing a world reaction.

Each strategy defines its prompt, structured output type, allowed operations and
evidence view. Strategies that need rules or older history bind the two
read-only tools **lookup_rule** and **recall_history**, capped at three calls
per decision, as described in game-flow.v2.md. Validate every proposed
operation and reference. Retry invalid model output only within a small fixed
budget.

Narration is a separate, unbound model call. It receives public situation data,
the accepted player action and recorded public results. It returns a
checkpointed **BeatDraft** and performs no write. A later **record_beat**
operation persists that draft.

Minimal tests:

- reject an unknown operation and an out-of-situation reference;
- narration receives no private check data and has no bound tools;
- the beat draft survives until **record_beat** completes.

### 6. Implement the deterministic scheduler

Implement **advance** as a pure priority function over checkpoint state and a
fresh situation:

1. terminal run condition;
2. unresolved successful hit and required damage flow;
3. pending player request or submitted response;
4. incomplete current action;
5. side initiative or the next eligible combat actor;
6. queued world and monster reactions;
7. pending narration beat or draft;
8. turn closure.

Emit exactly one **NextEffect**. The combat cursor's stable order and index
establish which actors have acted; do not maintain a second action map or infer
turns from events. Recompute eligibility after every mutation so down, absent,
moved or non-hostile actors are skipped.

Minimal tests:

- one table-driven test covers all priorities and ties;
- side initiative is settled once, with the hero side winning a tie;
- every eligible hostile acts once in an admitted round;
- turn closure is refused while any earlier obligation remains.

### 7. Implement the five node functions

Implement the functions without composing the graph:

1. **advance** selects one effect and is the only router.
2. **decide** invokes one decision strategy and stores its validated result.
3. **execute** runs one operation handler and stores its result.
4. **await_player** interrupts with the checkpointed public request. On resume,
   it validates and stores the response without writing before the interrupt.
5. **narrate** makes one tool-free model call and stores a beat draft.

Every worker returns control to **advance**. Keep retryable model failures,
structured mechanic refusals and infrastructure failures distinct.

Minimal tests: one test for each node boundary, including interrupt and resume.

### 8. Simplify the turn entry point and prepare scenarios

1. Resolve authentication and ownership at the route and game-service boundary.
2. Translate opening, a new player action, a Roll response, a choice response
   and an authenticated retry into typed graph input.
3. Record a new player action through playthrough service before graph
   execution.
4. Validate resume input against the checkpointed request. Stop inferring
   control flow from transcript order or an open-turn scan.
5. Preserve the current HTTP input and **awaiting** response shape unless a
   concrete implementation constraint requires a wire change.
6. Prepare scripted model decisions and fixtures for the behavioral catalog in
   **docs/general/game-flow.v2.examples.md**.

Keep four end-to-end graph scenarios:

1. opening followed by NPC conversation;
2. active investigation across a Roll interrupt and process restart;
3. movement or a fixture consequence that changes durable world state;
4. side initiative, hero attack and damage, all eligible hostile actions,
   combat continuation, and terminal defeat.

Fold ambiguity into the combat scenario. Cover rules lookup and history recall
at their tool and projection boundaries instead of adding broad graph
tests.

### 9. Compose the graph last and remove superseded artifacts

After steps 1 through 8 pass their focused tests:

1. Add **advance**, **decide**, **execute**, **await_player** and **narrate**.
2. Add **START → advance**.
3. Add one conditional route from **advance** to the four workers or **END**,
   based only on **NextEffect**.
4. Add one fixed edge from every worker back to **advance**.
5. Compile with the existing durable checkpointer keyed by the run's thread.
6. Run the four prepared end-to-end scenarios and one topology assertion.
7. Delete the old tool loop, guard, combat-specific nodes, message-state
   helpers, obsolete prompts, tests and imports.
8. Delete **backend/graph.png** and other old graph artifacts.
9. Update module READMEs, architecture, requirement mapping and the documentation
   index.
10. Search for removed names and unused artifacts before declaring the refactor
    complete.

Do not add subgraphs, node-specific routers, direct worker-to-worker edges or
**Command(goto=...)**. A sixth node requires a distinct durability or execution
boundary that none of the reviewed scenarios fits.

## Verification

Run the smallest relevant checks after each step, then finish with:

```bash
make backend-lint
make backend-test
```

Run frontend tests and type checking only if the turn response contract or
frontend code changes. No database migration or new constraint test is expected.

## Acceptance criteria

- The graph has exactly the five planned nodes and one router.
- Every roll and mutation uses a deterministic playthrough service.
- Active requests, operation results, hits, rolls and combat order survive
  restart in LangGraph state without workflow tables.
- Player roll and choice requests resume without revealing private mechanics.
- Every eligible hostile acts according to the combat cursor; down, moved, and
  non-hostile actors do not.
- Narration uses recorded public outcomes and cannot call tools; the only
  bound tools are the read-only knowledge tools inside `decide`.
- Expected refusals are typed results; integrity and infrastructure failures are
  errors.
- The turn API supports openings, actions, requests, resumes, and narration.
- The four end-to-end scenarios pass.
- No migration adds operation, request or event-consumption persistence.
- No obsolete graph code, tests, prompts, imports, or generated artifacts
  remain.
