"""Sprint 010/11 round 4, Faults B and C -- ← finding: a `tool_call
attack` recorded `hit` while the narration said "fails to connect", and a
character brought to 0 HP (`down: true`) was narrated standing "ready for
your next move"; separately, three monster attack rolls were made through
`roll_dice` and never followed by `attack`, and the model decided the
miss itself.

`agent.nodes._turn_mechanics_summary` is this turn's own ground truth,
rebuilt from the events it has already written -- driven directly here
(no graph, no LLM), the same bare-`SimpleNamespace`-events seam
`test_run_turn_engine.py` and `test_lookup_rule_visible_entry.py` already
use for a tool/node's own reads."""

import asyncio

from app.modules.game.agent import nodes
from app.modules.game.agent.state import DmContext

RUN_ID = "run-1"
TURN_ID = "turn-1"


class _Event:
    def __init__(self, event_id: str, type_: str, payload: dict) -> None:
        self.id = event_id
        self.type = type_
        self.payload = payload


class _FakeDb:
    def __init__(self, events: list[_Event]) -> None:
        self._events = events

    async def execute(self, statement):
        events = self._events

        class _Result:
            def scalars(self):
                return self

            def all(self):
                return events

        return _Result()


def _ctx(events: list[_Event]) -> DmContext:
    return DmContext(
        db=_FakeDb(events), user_id="user-1", actor_id="actor-1", run_id=RUN_ID, turn_id=TURN_ID
    )


def _summary(events: list[_Event]) -> str:
    return asyncio.run(nodes._turn_mechanics_summary(_ctx(events)))


def test_no_events_this_turn_produce_no_summary():
    assert _summary([]) == ""


def test_a_landed_attack_and_a_downed_character_are_both_stated_as_ground_truth():
    events = [
        _Event(
            "e1",
            "tool_call",
            {
                "name": "attack",
                "args": {"actorId": "goblin-1", "targetId": "hero-1"},
                "rollIds": ["roll-1"],
                "result": "ok",
                "outcome": {"outcome": "hit", "total": 15, "natural": 11, "armourClass": 13},
            },
        ),
        _Event(
            "e2",
            "hp_changed",
            {
                "targetId": "hero-1",
                "targetName": "Hero",
                "before": 4,
                "after": 0,
                "max_hp": 12,
                "alive": True,
                "down": True,
            },
        ),
    ]

    summary = _summary(events)

    assert "ATTACK: goblin-1 vs hero-1 -> hit" in summary
    assert "HP CHANGED: Hero 4 -> 0 (DOWN)" in summary
    assert "never describe any creature" in summary
    assert "never say an attack landed when it recorded a miss" in summary.lower()


def test_a_monster_reduced_to_zero_hp_is_stated_as_dead_not_down():
    """Live check, round 4 -- ← finding: a goblin brought to 0 HP
    (`alive: false`) was still narrated as staggering but standing. `down`
    only ever applies to a player character; a monster's own death reads
    as `dead`, and the rule below must say so explicitly."""
    events = [
        _Event(
            "e1",
            "hp_changed",
            {
                "targetId": "goblin-1",
                "targetName": "Goblin Raider",
                "before": 4,
                "after": 0,
                "max_hp": 7,
                "alive": False,
                "down": False,
            },
        ),
    ]

    summary = _summary(events)

    assert "HP CHANGED: Goblin Raider 4 -> 0 (dead)" in summary
    assert "a monster dead, defeated or destroyed" in summary


def test_a_missed_attack_is_stated_as_a_miss():
    events = [
        _Event(
            "e1",
            "tool_call",
            {
                "name": "attack",
                "args": {"actorId": "goblin-1", "targetId": "hero-1"},
                "rollIds": ["roll-1"],
                "result": "ok",
                "outcome": {"outcome": "miss", "total": 9, "natural": 5, "armourClass": 13},
            },
        ),
    ]

    summary = _summary(events)

    assert "ATTACK: goblin-1 vs hero-1 -> miss" in summary


def test_an_attack_roll_never_consumed_by_attack_is_flagged_unresolved():
    """Fault B -- ← finding: `roll_dice(kind="attack")` was made and never
    followed by `attack`; the model decided the outcome itself. The roll
    stays a legitimate first step (it is `attack`'s own `roll_id`
    argument), but an unconsumed one must read as unresolved, not as a
    result to narrate."""
    events = [
        _Event(
            "roll-1",
            "roll",
            {
                "kind": "attack",
                "actorId": "goblin-1",
                "formula": "1d20+4",
                "faces": [5],
                "modifier": 4,
                "total": 9,
            },
        ),
    ]

    summary = _summary(events)

    assert "UNRESOLVED attack roll (total 9) for actor goblin-1" in summary
    assert "do not narrate a hit, miss, or damage for this roll" in summary


def test_a_roll_consumed_by_its_matching_attack_is_not_flagged_unresolved():
    events = [
        _Event(
            "roll-1",
            "roll",
            {
                "kind": "attack",
                "actorId": "goblin-1",
                "formula": "1d20+4",
                "faces": [11],
                "modifier": 4,
                "total": 15,
            },
        ),
        _Event(
            "e1",
            "tool_call",
            {
                "name": "attack",
                "args": {"actorId": "goblin-1", "targetId": "hero-1"},
                "rollIds": ["roll-1"],
                "result": "ok",
                "outcome": {"outcome": "hit", "total": 15, "natural": 11, "armourClass": 13},
            },
        ),
    ]

    summary = _summary(events)

    assert "UNRESOLVED attack roll" not in summary


def test_a_check_or_damage_roll_is_never_flagged_unresolved():
    """Only `attack`/`damage` rolls are ever consumed by a matching tool
    call -- an `ability_check`/`saving_throw`/`initiative`/`custom` roll is
    resolved a different way (`resolve_check`/`resolve_save`, or simply
    read by the narration) and must never be misreported as unresolved."""
    events = [
        _Event(
            "roll-1",
            "roll",
            {
                "kind": "ability_check",
                "actorId": "hero-1",
                "formula": "1d20+3",
                "faces": [12],
                "modifier": 3,
                "total": 15,
            },
        ),
    ]

    assert _summary(events) == ""


def test_missing_turn_id_or_db_degrades_to_no_summary():
    ctx = DmContext(db=None, user_id="user-1", run_id=RUN_ID, turn_id=None)
    assert asyncio.run(nodes._turn_mechanics_summary(ctx)) == ""
