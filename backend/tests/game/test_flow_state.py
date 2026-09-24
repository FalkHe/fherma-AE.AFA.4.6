"""Sprint 011/05, WI1 -- flow_state round-trips through the checkpointer's
own serializer and the two pure clearers do exactly what they promise."""

from dataclasses import replace

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.modules.game.agent.flow_state import (
    ActionCursor,
    AwaitingRef,
    CombatCursor,
    GameFlowState,
    NarrativeCursor,
    OperationKind,
    TurnFrame,
    close_turn_state,
    end_combat_state,
)


def _state() -> GameFlowState:
    awaiting = AwaitingRef(
        request_id="01AWAITINGREF00000000000",
        kind="roll",
        actor_id="hero-1",
        public={"ability": "dex", "skill": None, "dc": 15},
        consumer=OperationKind.RESOLVE_CHECK,
        consumer_payload={"dc": 15},
    )
    combat = CombatCursor(
        scene_id="scene-1",
        order=("hero-1", "goblin-1"),
        index=0,
        round=1,
        round_admitted=True,
        winning_side="hero",
    )
    return GameFlowState(
        turn=TurnFrame(
            run_id="run-1",
            hero_id="hero-1",
            turn_id="turn-1",
            input_kind="action",
            text="I attack",
            status="open",
            round_admitted=True,
        ),
        move=None,
        action=ActionCursor(
            action_id="action-1",
            actor_id="hero-1",
            kind="attack",
            plan=(),
            step_index=0,
            status="planned",
            roll_id=None,
            roll_consumed=False,
        ),
        combat=combat,
        awaiting=awaiting,
        pending_hit_id=None,
        reactions=[],
        narrative=NarrativeCursor(beat_id=None, draft=None, event_id=None),
        effect=None,
        result=None,
        usage=None,
        error=None,
    )


def test_state_round_trips_through_the_checkpoint_serializer():
    serde = JsonPlusSerializer()
    state = _state()

    type_, blob = serde.dumps_typed(state)
    restored: GameFlowState = serde.loads_typed((type_, blob))

    # msgpack has no tuple type; every sequence round-trips as a list, so
    # `order` is normalised back before comparing the rest field-by-field.
    restored_combat = replace(restored["combat"], order=tuple(restored["combat"].order))

    assert restored["awaiting"] == state["awaiting"]
    assert restored_combat == state["combat"]


def test_close_turn_state_clears_turn_local_keys_and_keeps_combat():
    state = _state()

    delta = close_turn_state(state)

    assert delta["awaiting"] is None
    assert delta["move"] is None
    assert delta["action"] is None
    assert delta["result"] is None
    assert delta["effect"] is None
    assert delta["error"] is None
    assert delta["reactions"] == []
    assert delta["narrative"] == NarrativeCursor(beat_id=None, draft=None, event_id=None)
    assert "combat" not in delta
    assert "turn" not in delta


def test_end_combat_state_clears_combat_only():
    state = _state()

    delta = end_combat_state(state)

    assert delta == {"combat": None}
