---
author: fhit:architect
owner: agent
created: 2026-09-24
---
# Research: sprint 011/03 — durable world changes

## Facts

- Fixture success is prose only: `interact` returns `bool`, writes a `way_opened` event and a `tool_call`, and touches no row — `backend/app/modules/playthrough/service.py:2051` (docstring says "no `objects` row ever changes here"), event write at `:2216`. Refusal path commits a `dm` `tool_call` then raises: `:2013`.
- `GameObject.state` is free JSONB (`backend/app/modules/playthrough/models.py:183`); already used for `down` (`service.py:423`, `:3052`) and character sheet (`schemas.py:270`). Whole-object reassignment is the house rule (`model_copy(update=...)`), never in-place mutation.
- `use_exit(db, *, user_id, actor_id, exit_id) -> None`, no `turn_id`, appends `scene_entered` or `adventure_completed`, sets `run.status = "finished"` on the last adventure, then a `dm` `tool_call` and one commit — `service.py:1899`; refusal `_refuse_exit` `:1872` raises `ExitNotAvailableError`.
- `take`/`drop`/`give`/`use_item` all return `None` (`:2322`, `:2406`, `:2475`, `:2573`); refusals go through `_refuse_move` `:2290` and raise. `use_item` is unconditional refusal (`ItemNotConsumableError`, `errors.py:305`).
- Typed-result precedent already exists from sprint 02: frozen dataclasses `InitiativeResult`/`AttackResult`/`DamageResult` in `backend/app/modules/playthrough/schemas.py:511-554`, no `refused` member.
- Scans: `_roll_already_spent` `:1656`, `_already_acted` `:1676` (+`_ACTION_NAMES` `:1674`), `_hit_already_damaged` `:2859` — all read `tool_call` payloads for the run+turn. `_already_acted` is called by `interact:2114`, `take:2353`, `give:2509`, `use_item:2601`, `attack:2723`; `_hit_already_damaged` only by `_consume_hit:2914`; `_roll_already_spent` only by `_consume_roll` (keep — sprint 05 owns the roll cursor; the intent removes only `_already_acted`, spent-roll and damaged-hit scans, so drop `_hit_already_damaged` with `_consume_hit` falling back to hit identity alone, and keep `_roll_already_spent` until the cursor exists unless it is already free of callers).
- Game-module writes to delete: `backend/app/modules/game/service.py:252-263` (question answer `player_action` + `commit`), `backend/app/modules/game/agent/nodes.py:389-397` (`record_action`), `:514-523` (`record_narration` + `activate_campaign_run`). `append_event` itself only adds/flushes; the caller owns the commit (`service.py:3111`).
- Run status values: `setup|ready|active|archived|finished` (`models.py:40`); `finished` is set only inside `use_exit`. No column carries *how* it ended and the persistence boundary forbids one, so victory/defeat/authored must be an event payload plus `status="finished"`.
- Creature templates carry `disposition` as free prose only (`backend/app/modules/content/schemas.py:57`) — hostility has no field; it belongs in `GameObject.state`.
- `ask_player` already appends `question` and commits (`service.py:1614`); `record_rule_lookup` `:3225` is the model for a recording function.
- Tests that break (delete, do not port): `tests/playthrough/test_service_one_action_per_turn.py`, `tests/playthrough/test_acceptance_interact_and_one_action.py` (one-action half), the `use_item` and already-acted cases in `tests/playthrough/test_service_inventory_moves.py:307,651` and `tests/playthrough/test_acceptance_inventory_moves.py`, `tests/game/test_service.py` (`use_item` tool, answer commit), `tests/game/test_run_turn_engine.py` (`record_action`/`record_narration`), `tests/playthrough/test_service_use_exit.py` + `test_acceptance_exits_and_endings.py` (return type).

## Work items

- WI1 fixture, exit and items: persist the fixture outcome in object state, return `MutationResult` from `interact`/`take`/`drop`/`give`/`use_exit`, add `turn_id` to `use_exit`, delete `use_item`, `_already_acted`, `_ACTION_NAMES`, `_hit_already_damaged` and their call sites, adjust the tools in `game/agent/tools.py` to the new returns.
- WI2 world and lifecycle functions: `set_hostility`, `leave_scene`, `enter_next_adventure` (thin graph-facing wrapper over `enter_adventure`) and `finish_run` for victory, defeat and authored endings.
- WI3 recording functions and the game module's retreat: `record_player_action`, `record_answer`, `record_narration` (with usage and the `ready → active` activation), `record_outcome`; remove every `commit`/`append_event` from `game/service.py` and `game/agent/nodes.py`.

WI1 and WI2 run in parallel (disjoint functions); WI3 depends only on the shared result type, so it may start once WI1 has landed `MutationResult` — land that type first in WI1's initial commit.

## Interfaces

```python
@dataclass(frozen=True)
class MutationResult:                 # playthrough/schemas.py, internal only
    status: Literal["ok", "refused"]
    reason: str | None = None         # refusal text, mirrored into the dm tool_call
    event_ids: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
```

Signatures (all `async`, all `db: AsyncSession` first, all keyword-only after):

```python
interact(*, user_id, actor_id, object_id, action, roll_id=None, turn_id=None) -> MutationResult
    # facts: {"success": bool, "dc": int, "total": int|None, "bypassedBy": str|None, "outcome": str}
take(*, user_id, actor_id, item_id, turn_id=None) -> MutationResult
drop(*, user_id, actor_id, item_id, turn_id=None) -> MutationResult
give(*, user_id, from_id, to_id, item_id, turn_id=None) -> MutationResult
use_exit(*, user_id, actor_id, exit_id, turn_id=None) -> MutationResult
    # facts: {"kind": "scene"|"adventure_end", "sceneId": str|None, "runFinished": bool}
set_hostility(*, user_id, actor_id, hostile: bool, turn_id=None) -> MutationResult
leave_scene(*, user_id, actor_id, turn_id=None) -> MutationResult
enter_next_adventure(*, user_id, run_id, turn_id=None) -> MutationResult
finish_run(*, user_id, run_id, outcome: Literal["victory","defeat","authored"], turn_id=None) -> MutationResult
record_player_action(*, user_id, run_id, text, turn_id, answers_question_id=None) -> Event
record_answer(*, user_id, run_id, text, question_id, turn_id) -> Event
record_narration(*, user_id, run_id, text, turn_id, usage=None) -> Event
record_outcome(*, user_id, run_id, name, args, outcome, turn_id, roll_ids=()) -> Event
```

Object-state JSON keys (`GameObject.state`, reassigned whole):

- fixture: `state["fixture_outcomes"][<action>] = {"success": <authored success prose>, "turnId": <turn_id|null>}`; a key present means the fixture stays open across reloads (AC1).
- creature: `state["hostile"]: bool` — absent means "not yet decided", the situation falls back to authored disposition prose.
- departure: `state["left_scene"] = {"sceneId": str, "adventureRunId": str}` written while `scene_id`/`adventure_run_id` are cleared together (the `position` CHECK allows only both or neither).

Refusal convention: expected mechanic refusals (unreachable item, unmatched exit, unmatched fixture action, missing bypass item) return `MutationResult(status="refused", reason=…)` after the existing `dm` `tool_call` refusal row, and raise nothing. `GameObjectNotFoundError`, `CampaignRunNotFoundError`, `RunArchivedError`, `InvalidRunStatusError`, `RollNotFoundError`, `RollNotUsableError` and payload/infrastructure errors keep raising; `AlreadyActedError` and `ItemNotConsumableError` are deleted with their mechanics.

Run ending: `finish_run` sets `status="finished"` and appends one `system` event at `player` visibility, `{"message": <ending text>, "details": {"outcome": "victory"|"defeat"|"authored"}}` — no column, no migration. `use_exit`'s own last-adventure branch calls `finish_run(outcome="authored")` rather than setting the status itself.

## Open questions

None product-visible.
