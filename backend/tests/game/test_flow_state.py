"""Sprint 011/05, WI1 -- flow_state round-trips through the checkpointer's
own serializer and the two pure clearers do exactly what they promise.

Sprint 011/08 live-check fix: the round-trip now goes through
`checkpointer_service.checkpoint_serde()` - the same serde both
`AsyncPostgresSaver` and the `InMemorySaver()` fallback are built with -
under `LANGGRAPH_STRICT_MSGPACK=true` (pinned by `tests/conftest.py`), so a
flow-state dataclass that isn't registered fails this test the same way it
would get silently blocked (or, pre-fix, warned about) in production."""

from app.core.checkpointer import service as checkpointer_service
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


def test_state_round_trips_through_the_app_configured_serde_under_strict_msgpack():
    """`checkpoint_serde()` is what `checkpointer()` and `build_agent()`'s
    `InMemorySaver()` fallback actually use in production - this proves it
    restores every flow-state dataclass byte-for-byte even with
    `LANGGRAPH_STRICT_MSGPACK=true` set (← `tests/conftest.py`), which
    blocks any type `allowed_msgpack_modules` doesn't name."""
    serde = checkpointer_service.checkpoint_serde()
    state = _state()

    type_, blob = serde.dumps_typed(state)
    restored: GameFlowState = serde.loads_typed((type_, blob))

    assert restored["awaiting"] == state["awaiting"]
    assert restored["combat"] == state["combat"]
    assert isinstance(restored["combat"].order, tuple)
    assert isinstance(restored["action"].plan, tuple)
    assert restored == state


def test_close_turn_state_clears_turn_local_keys_and_keeps_combat():
    state = _state()

    delta = close_turn_state(state)

    assert delta["awaiting"] is None
    assert delta["move"] is None
    assert delta["action"] is None
    assert delta["pending_hit_id"] is None
    assert delta["result"] is None
    assert delta["usage"] is None
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
