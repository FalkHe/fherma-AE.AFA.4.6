"""Sprint 010/10, ← finding: a monster's own turn aimed an attack at the
wrong creature (an NPC with no attacks, not one of several identically-
named monsters) and, once that failed, the tool's bare "refused: <message>"
gave the model nothing to act on -- it gave up and narrated a resolution no
tool had produced instead.

These drive `roll_dice`/`attack`/`damage`/`get_scene`'s own coroutine
directly (`tool.coroutine`, the plain `async def` LangChain wraps -- a
`ToolRuntime` stand-in needs only the one attribute, `.context`, every
tool actually reads) against the real `playthrough.service` functions, so
the lookup failures these tests assert on are the real
`GameObjectNotFoundError`/`ValueError` those raise, not a stubbed one.
No real model call anywhere in this file.
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.modules.game.agent import tools
from app.modules.game.agent.state import DmContext
from app.modules.playthrough.errors import HitNotUsableError, ObjectNotReachableError


class _EmptyDb:
    """Every query answers "nothing found" -- `resolve_actor_ref`,
    `describe_scene_creatures` and every mechanic's own actor/target
    lookup all naturally fail against this, so a tool exercised here is
    proven to degrade to a structured hint rather than raise or crash."""

    async def execute(self, statement):
        class _Result:
            def scalar_one_or_none(self):
                return None

            def scalars(self):
                return self

            def all(self):
                return []

        return _Result()

    async def get(self, model, pk):
        return None


def _runtime(**overrides) -> SimpleNamespace:
    defaults = dict(
        db=_EmptyDb(), user_id="user-1", actor_id="hero-1", run_id="run-1", turn_id="turn-1"
    )
    defaults.update(overrides)
    return SimpleNamespace(context=DmContext(**defaults))


# --- roll_dice --------------------------------------------------------------


def test_roll_dice_hands_back_a_structured_hint_when_the_actor_cannot_be_found():
    result = asyncio.run(
        tools.roll_dice.coroutine(
            kind="attack",
            context=tools.RollContext(),
            runtime=_runtime(),
            actor_id="mystery-goblin",
        )
    )

    assert result["status"] == "actor_not_found"
    assert "mystery-goblin" in result["message"]
    assert result["living_creatures"] == []


def test_roll_dice_hands_back_a_structured_hint_when_the_actor_has_no_attacks(monkeypatch):
    async def no_attacks(*args, **kwargs):
        raise ValueError("this actor has no attacks")

    monkeypatch.setattr(tools.playthrough_service, "roll", no_attacks)

    result = asyncio.run(
        tools.roll_dice.coroutine(
            kind="attack", context=tools.RollContext(), runtime=_runtime(), actor_id="hero-1"
        )
    )

    assert result["status"] == "no_attack"
    assert result["actor_id"] == "hero-1"
    assert "no attacks" in result["message"]


def test_roll_dice_still_raises_a_non_attack_failure_rather_than_hinting(monkeypatch):
    # Only attack/damage rolls get the actionable hint -- anything else
    # (an ability check with a bad ability name, say) still raises, exactly
    # the pre-existing behaviour `test_service.py`'s own
    # `test_tool_failure_is_caught_and_narrated_without_crashing` covers at
    # the graph level.
    async def boom(*args, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(tools.playthrough_service, "roll", boom)

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(
            tools.roll_dice.coroutine(
                kind="ability_check",
                context=tools.RollContext(ability="strength"),
                runtime=_runtime(),
                actor_id="hero-1",
            )
        )


# --- attack -------------------------------------------------------------


def test_attack_hands_back_a_structured_hint_when_the_actor_cannot_be_found():
    result = asyncio.run(
        tools.attack.coroutine(
            target_id="hero-1", roll_id="roll-1", runtime=_runtime(), actor_id="mystery-goblin"
        )
    )

    assert result["status"] == "actor_not_found"
    assert result["living_creatures"] == []


def test_attack_hands_back_a_structured_hint_when_the_actor_is_not_in_the_scene(monkeypatch):
    async def out_of_scene(*args, **kwargs):
        raise ObjectNotReachableError("target-1")

    monkeypatch.setattr(tools.playthrough_service, "attack", out_of_scene)

    result = asyncio.run(
        tools.attack.coroutine(
            target_id="target-1", roll_id="roll-1", runtime=_runtime(), actor_id="hero-1"
        )
    )

    assert result["status"] == "not_in_scene"
    assert result["actor_id"] == "hero-1"


# --- damage ---------------------------------------------------------------


def test_damage_hands_back_a_not_found_hint_for_an_unknown_target():
    result = asyncio.run(
        tools.damage.coroutine(
            target_id="mystery", roll_id="roll-1", hit_id="hit-1", runtime=_runtime()
        )
    )

    assert result["status"] == "not_found"
    assert result["living_creatures"] == []


def test_damage_hands_back_a_rejected_status_for_an_unusable_hit(monkeypatch):
    async def stale_hit(*args, **kwargs):
        raise HitNotUsableError("hit-1")

    monkeypatch.setattr(tools.playthrough_service, "damage", stale_hit)

    result = asyncio.run(
        tools.damage.coroutine(
            target_id="target-1", roll_id="roll-1", hit_id="hit-1", runtime=_runtime()
        )
    )

    assert result["status"] == "rejected"
    assert "living_creatures" not in result


# --- get_scene --------------------------------------------------------------


def test_get_scene_includes_the_runs_own_living_creatures(monkeypatch):
    canned = [
        {
            "id": "gob-1",
            "name": "Goblin Raider",
            "role": "monster",
            "is_alive": True,
            "current_hp": 7,
            "max_hp": 7,
            "armour_class": 13,
            "attacks": ["Sling"],
        }
    ]

    async def fake_describe(*args, **kwargs):
        return canned

    monkeypatch.setattr(tools.playthrough_service, "describe_scene_creatures", fake_describe)

    result = asyncio.run(
        tools.get_scene.coroutine(
            scene_id="village-green",
            runtime=_runtime(),
            campaign_id="greenhollow",
            version="v1",
        )
    )

    assert result["creatures_present"] == canned


def test_get_scene_degrades_to_no_creatures_when_the_run_cannot_be_read():
    # No monkeypatch here: `describe_scene_creatures` runs for real against
    # `_EmptyDb` and fails to read a run at all -- `get_scene` must still
    # return the scene's own authored facts, exactly `_build_game_context`'s
    # own defensive pattern (`agent/nodes.py`).
    result = asyncio.run(
        tools.get_scene.coroutine(
            scene_id="village-green",
            runtime=_runtime(),
            campaign_id="greenhollow",
            version="v1",
        )
    )

    assert result["creatures_present"] == []
    assert result["title"]
