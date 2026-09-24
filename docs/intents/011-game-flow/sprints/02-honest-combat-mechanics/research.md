---
author: fhit:architect
owner: agent
created: 2026-09-24
---
# Research: sprint 02 — honest combat mechanics

## Facts

**Initiative.** `service.roll_initiative` (`service.py:1479`) is a thin pair of
side rolls: `_roll_for_side` (`service.py:1444`) asks the first member-owned id
of a side through `request_player_roll`, otherwise rolls the side's *first* id
outright at `player` visibility; it returns `tuple[Event, Event]` and settles
nothing — no order, no winner, no tie rule, no stored fight state (docstring
`service.py:1495-1500`). The hostile side therefore already gets one automatic
roll; what is missing is settlement: compare totals, hero side wins a tie, emit
one stable actor order. The dexterity formula is already derived server-side
(`dice.derive_formula`, `dice.py:251-253`). The graph will call this as
`settle_initiative` (`docs/general/game-flow.v2.md:458`); the cursor that stores
the order is sprint 05 (`game-flow.v2.md:333-349`), so this sprint only returns
it.

**Sides.** There is no role or hostility column and no authored flag:
`describe_scene_creatures` derives `role` as `player` when `member_id` is set,
else `monster` when the template's stat block has attacks, else `npc`
(`service.py:1160`, docstring `:1123-1131`). `CreatureTemplate.disposition` is
prose only (`backend/app/modules/content/schemas.py:57`), so it cannot be parsed
at runtime; hostility overrides live in object `state` (intent §1.6,
`set_hostility`, not this sprint). Hero side = `member_id is not None`.

**Attack.** `attack` returns a bare string `"hit" | "crit" | "miss"`
(`service.py:2614`, `:2758`) and records the outcome on a `tool_call`. The hit
identity is the id of that `tool_call` event, which the caller re-discovers by
querying the newest `tool_call` of the turn (`game/agent/tools.py:864-876`) — a
guess that breaks whenever any other event is appended between. Natural 20 is
read off `faces[0]` (`service.py:2726`).

**Damage.** `damage` returns `int` applied (`service.py:2850`, `:2983`) and
consumes a roll whose formula came from `attack.damage` verbatim
(`dice.py:239`). Nothing doubles dice on a critical — the crit outcome reaches
`damage` only as the consumed `hit_id`, so today a crit applies normal damage
(intent "Change" row). The single derivation point for doubling is
`derive_formula` at `dice.py:236-239`: double the parsed dice count only, leave
the flat modifier untouched, so a critical `1d8+3` becomes `2d8+3`.

**HP / alive / down disagreement.** `damage` sets `is_alive = False` only for
non-members; a downed hero keeps `is_alive = True` and records `down` in its
JSON `state` (`service.py:2935-2944`, `schemas.py:272-291`). Every read then
reports only `is_alive`: `describe_scene_creatures` emits `is_alive`
(`service.py:1165`) with no `down`, the tools' live-creature hint filters on it
(`tools.py:118`), `resolve_actor_ref` selects `is_alive.is_(True)`
(`service.py:1074`), and `character_read` returns neither flag
(`service.py:403-421`, feeding `get_table` `service.py:598`). Concretely: a hero
at 0 hp is still listed as a living, targetable, name-resolvable actor. Only the
`hp_changed` and `damage` events carry `down` (`service.py:2958`, `:2978`).

**Tests that break.** `tests/playthrough/test_service_roll_initiative.py` (480
lines) asserts the old composition only — trim to the derived-roll and
settlement cases. `test_service_attack_and_damage.py` (1238) and
`test_acceptance_fight_in_the_transcript.py:1166` assert the string/int returns.
`tests/game/test_service.py:551-615` asserts the `roll_initiative` tool shape.
`test_dice.py` gains the crit-formula case.

## Work items

- **WI1 initiative** (`service.py`, `tests`): `roll_side_initiative` +
  `settle_initiative` returning `InitiativeResult`; delete `_roll_for_side` and
  the old `roll_initiative`; adjust the `roll_initiative` tool to call both and
  keep returning its current dict plus `order`.
- **WI2 attack, damage, crit** (`service.py`, `dice.py`): typed `AttackResult`
  and `DamageResult`; critical dice doubling in `derive_formula`; adjust the two
  tool call sites and delete the newest-event hit-id query.
- **WI3 down consistency** (`service.py`, reads): one `is_down(obj)` helper used
  by mutation and every read; runs after WI2, which fixes its write side. WI1
  and WI2 run in parallel.

## Interfaces

```python
# playthrough/schemas.py — plain dataclasses, internal, not wire shapes
@dataclass(frozen=True)
class InitiativeResult:
    hero_total: int; hostile_total: int
    hero_roll_id: str; hostile_roll_id: str
    winning_side: Literal["hero", "hostile"]   # tie -> "hero"
    order: list[str]                            # stable actor ids, winner first

@dataclass(frozen=True)
class AttackResult:
    status: Literal["hit", "miss", "critical"]
    hit_id: str | None                          # tool_call event id; None on miss
    total: int; natural: int; armour_class: int

@dataclass(frozen=True)
class DamageResult:
    applied: int; current_hp: int; max_hp: int
    is_alive: bool; down: bool

async def roll_side_initiative(db, *, user_id, run_id, hero_ids, hostile_ids,
                               turn_id=None) -> tuple[Event, Event]
async def settle_initiative(db, *, user_id, run_id, hero_ids, hostile_ids,
                            turn_id=None) -> InitiativeResult
async def attack(...) -> AttackResult          # signature otherwise unchanged
async def damage(..., critical: bool = False) -> DamageResult
def dice.derive_formula(..., context={"critical": True}) -> str  # doubles dice only
def is_down(obj: GameObject) -> bool           # member at 0 hp, or not is_alive
```

Old callers: the `roll_initiative` tool (`tools.py:361`) calls
`settle_initiative` and reports both roll events plus `order`; the `attack` tool
reads `result.status`/`result.hit_id` instead of scanning events; the `damage`
tool reads `result.applied`. Reads add `down` alongside `is_alive`
(`describe_scene_creatures`, `character_read`), and `resolve_actor_ref` plus the
live-creature hint exclude downed actors.

## Open questions

- Is the fight order ever shown to the player? Today nothing displays it: only
  the two initiative roll events reach the transcript
  (`frontend/src/modules/play/transcript.ts:96`), and no event states who acts
  first. Confirm the order stays invisible, or a new player-visible event is
  needed.
- Should a downed hero's party card read "down" on the play screen, or keep
  showing 0 hp only?
