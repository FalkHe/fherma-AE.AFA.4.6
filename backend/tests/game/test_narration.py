"""`narration.narrate()`: evidence-only prompt building and the
draft-survives-until-recorded state rule (sprint 011/06, WI2)."""

import asyncio
import json
from dataclasses import dataclass

from langchain_core.messages import AIMessage

from app.modules.game.agent import narration
from app.modules.game.agent.flow_state import GameFlowState, TurnFrame, Usage
from app.modules.playthrough.situation import ActorView, SecretView, Situation
from tests.game.fakes import ScriptedChatModel


def _hero() -> ActorView:
    return ActorView(
        id="hero-1",
        name="Aria",
        role="hero",
        kind="player",
        current_hp=10,
        max_hp=10,
        armour_class=15,
        is_alive=True,
        down=False,
        disposition=None,
        hostile=False,
        attacks=(),
        inventory=(),
    )


def _situation() -> Situation:
    hero = _hero()
    return Situation(
        run_id="run-1",
        hero_id="hero-1",
        adventure_run_id="adv-1",
        scene_id="scene-1",
        campaign_title="Greenhollow",
        adventure_title="The Goblin Warren",
        scene_title="The Cave Mouth",
        truth=("a guard patrols nearby",),
        consequences=(),
        pressure=None,
        npc_intent="the goblin plans to flee at 20 dc if spotted",
        secrets=(
            SecretView(
                fact="a hidden door lies behind the altar",
                ability="wisdom",
                skill="perception",
                dc=17,
                discovered_by="",
            ),
        ),
        hero=hero,
        actors=(hero,),
        fixtures=(),
        loose_items=(),
        exits=(),
        recent=(),
    )


@dataclass
class _Ctx:
    situation: Situation
    model: ScriptedChatModel


def _state(text: str = "I search the altar") -> GameFlowState:
    turn = TurnFrame(
        run_id="run-1",
        hero_id="hero-1",
        turn_id="turn-1",
        input_kind="action",
        text=text,
        status="open",
        round_admitted=True,
    )
    return {"turn": turn}  # type: ignore[typeddict-item]


def test_prompt_carries_no_secret_dc_or_npc_intent_and_binds_no_tools():
    text = "You press against the altar, feeling for a seam."
    model = ScriptedChatModel([AIMessage(content=text)])
    ctx = _Ctx(situation=_situation(), model=model)
    request = narration.BeatRequest(
        beat_id="beat-1",
        kind="attempt",
        allowed_evidence_ids=(),
        payload={"action": "search the altar"},
    )

    draft = asyncio.run(narration.narrate(ctx, request, _state()))

    assert draft.text == text
    assert model.bind_tools_calls == 0

    facts = narration._facts(ctx, request, _state())
    rendered = json.dumps(facts, default=str)
    for forbidden in ("hidden door lies behind the altar", '"dc": 17', "goblin plans to flee"):
        assert forbidden not in rendered


def test_evidence_outside_the_allowlist_is_excluded():
    situation = _situation()
    ctx = _Ctx(situation=situation, model=ScriptedChatModel([]))
    request = narration.BeatRequest(
        beat_id="beat-1",
        kind="answer",
        allowed_evidence_ids=("event-allowed",),
        payload={},
    )

    facts = narration._facts(ctx, request, _state())

    assert facts["situation"]["recent"] == []


def test_draft_state_keeps_draft_until_recorded_state_clears_it():
    draft = narration.BeatDraft(beat_id="beat-1", text="You step forward.", usage=Usage(0, 0, None))

    delta = narration.draft_state(draft)
    cursor = delta["narrative"]
    assert cursor.beat_id == "beat-1"
    assert cursor.draft == "You step forward."
    assert cursor.event_id is None

    recorded = narration.recorded_state("beat-1", "event-9")
    recorded_cursor = recorded["narrative"]
    assert recorded_cursor.beat_id == "beat-1"
    assert recorded_cursor.draft is None
    assert recorded_cursor.event_id == "event-9"
