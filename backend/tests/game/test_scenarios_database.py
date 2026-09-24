"""Sprint 011/08, WI3 -- the four `docs/general/game-flow.v2.examples.md`
scenarios (AC2, AC4) driven straight through the real compiled graph
(`agent.graph.build_graph` + `agent.flow_nodes.set_runtime`), never through
`game.service.run_turn` (owned by a concurrent WI2 rewrite this file must
not depend on). Real playthrough services against a scratch database
(`playthrough_db`), a real `InMemorySaver`, and a `ScriptedChatModel`
standing in for every `decide()`/`narrate()` model call -- no dice are
scripted: `playthrough.dice._rng()` is monkeypatched to a fixed,
non-critical roll (← `dice.py`'s own test seam) so hits, damage and
initiative are deterministic without touching game logic.

Assertions follow transcript order, event linkage and `awaiting` -- never
node sequences (← brief)."""

import asyncio

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from sqlalchemy import text

from app.core.checkpointer import service as checkpointer_service
from app.core.ids import generate_id
from app.modules.game.agent import flow_nodes
from app.modules.game.agent.decisions import (
    MonsterActionOut,
    MoveAssessmentOut,
    ReadMoveOut,
    ReferenceJudgementOut,
)
from app.modules.game.agent.flow_state import TurnFrame
from app.modules.game.agent.graph import build_graph, initial_state
from app.modules.playthrough import dice
from app.modules.playthrough import service as playthrough_service

pytestmark = pytest.mark.database

CAMPAIGN_ID = "greenhollow"
VILLAGE_GREEN = "village-green"
THORNWAY = "thornway"
TO_THORNWAY = "to-thornway"
LAIR_MAW = "lair-maw"
GOBLIN_TEMPLATE = "goblin"
MIRA_TEMPLATE = "mira"


class _FixedRng:
    """`dice._rng()`'s own test seam: a moderate, always-hitting,
    never-critical face so combat, checks and initiative are deterministic
    without any of this file scripting a die itself. `1d20` -> 15 (a hit
    against every AC in this campaign, never a natural 20's crit-double);
    any smaller die -> its own third face (a plain, unremarkable damage
    roll)."""

    def randint(self, a: int, b: int) -> int:
        return 15 if b == 20 else min(b, 3)


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


async def _object_ids(session, run_id: str, *, template_id: str, scene_id: str) -> list[str]:
    rows = (
        await session.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = :template_id AND scene_id = :scene_id ORDER BY id"
            ),
            {"run_id": run_id, "template_id": template_id, "scene_id": scene_id},
        )
    ).all()
    return [row.id for row in rows]


async def _events_for_run(session, run_id: str) -> list:
    rows = (
        await session.execute(
            text(
                "SELECT id, type, turn_id, payload FROM events "
                "WHERE campaign_run_id = :run_id ORDER BY id"
            ),
            {"run_id": run_id},
        )
    ).all()
    return rows


async def _setup_run(db, *, username: str) -> tuple[str, str, str]:
    """Starts a run, builds the seed character and enters the adventure --
    the same path `test_concurrent_monster_rolls_database.py` walks.
    Returns `(owner_id, run_id, hero_id)`."""
    owner_id = generate_id()
    await _insert_user(db, owner_id, username=username)
    await db.commit()
    run = await playthrough_service.start_campaign_run(
        db, user_id=owner_id, campaign_id=CAMPAIGN_ID
    )
    character = await playthrough_service.create_character(db, user_id=owner_id, run_id=run.id)
    await playthrough_service.enter_adventure(db, user_id=owner_id, run_id=run.id)
    return owner_id, run.id, character.id


def _frame(
    *, run_id: str, hero_id: str, turn_id: str, input_kind: str, text: str | None
) -> TurnFrame:
    return TurnFrame(
        run_id=run_id,
        hero_id=hero_id,
        turn_id=turn_id,
        input_kind=input_kind,
        text=text,
        status="open",
        round_admitted=input_kind != "opening",
    )


async def _run_to_end(graph, config: dict) -> dict:
    """Drains every interrupt with no scripted resume of its own -- used
    only when the graph is expected to reach `END` without pausing."""
    result = await graph.ainvoke(None, config=config)
    assert "__interrupt__" not in result
    return result


@pytest.fixture(autouse=True)
def _fixed_dice(monkeypatch):
    monkeypatch.setattr(dice, "_rng", lambda: _FixedRng())


@pytest.mark.database
def test_opening_then_conversation_narrates_and_closes(playthrough_db, monkeypatch):
    async def scenario():
        from tests.game.fakes import ScriptedChatModel

        db = playthrough_db
        owner_id, run_id, hero_id = await _setup_run(db, username="opening-flow")

        saver = InMemorySaver(serde=checkpointer_service.checkpoint_serde())
        config = {"configurable": {"thread_id": run_id}}

        # --- Turn 1: the opening (no player input). --------------------
        scripted = ScriptedChatModel([AIMessage(content="The village green lies quiet.")])
        flow_nodes.set_runtime(flow_nodes.FlowRuntime(db=db, user_id=owner_id, model=scripted))
        graph = build_graph(model=scripted, checkpointer=saver)

        opening_frame = _frame(
            run_id=run_id, hero_id=hero_id, turn_id=generate_id(), input_kind="opening", text=None
        )
        result = await graph.ainvoke(initial_state(opening_frame), config=config)
        assert "__interrupt__" not in result

        # --- Turn 2: "I talk to Mira." ----------------------------------
        mira_ids = await _object_ids(db, run_id, template_id=MIRA_TEMPLATE, scene_id=VILLAGE_GREEN)
        assert mira_ids, "greenhollow/v1's village-green placement changed under this test"
        mira_id = mira_ids[0]

        talk_text = "I talk to Mira."
        talk_turn_id = generate_id()
        await playthrough_service.record_player_action(
            db, user_id=owner_id, run_id=run_id, text=talk_text, turn_id=talk_turn_id
        )
        talk_frame = _frame(
            run_id=run_id,
            hero_id=hero_id,
            turn_id=talk_turn_id,
            input_kind="action",
            text=talk_text,
        )

        talk_model = ScriptedChatModel(
            [
                # read_move's own tool loop: one non-tool reply, then the
                # structured decision -- no proposed operations (a pure
                # conversational move).
                AIMessage(content="Rosalind greets Mira."),
                ReadMoveOut(intent="talk", refs={"actor_id": mira_id}, proposed=None),
                "Mira tells you what she knows about the missing flock.",
            ]
        )
        flow_nodes.set_runtime(flow_nodes.FlowRuntime(db=db, user_id=owner_id, model=talk_model))
        graph2 = build_graph(model=talk_model, checkpointer=saver)
        result2 = await graph2.ainvoke({"turn": talk_frame}, config=config)
        assert "__interrupt__" not in result2

        rows = await _events_for_run(db, run_id)
        by_turn = [row for row in rows if row.turn_id == talk_frame.turn_id]
        kinds = [row.type for row in by_turn]

        assert "player_action" in kinds
        action_index = kinds.index("player_action")
        narration_indices = [i for i, k in enumerate(kinds) if k == "narration"]
        assert narration_indices, kinds
        assert narration_indices[-1] > action_index, kinds

        opening_rows = [row for row in rows if row.turn_id == opening_frame.turn_id]
        assert any(row.type == "narration" for row in opening_rows), opening_rows

        awaiting = await playthrough_service.get_awaiting(db, user_id=owner_id, run_id=run_id)
        assert awaiting == "none"

    asyncio.run(scenario())


@pytest.mark.database
def test_active_investigation_pauses_for_a_roll_then_restarts(playthrough_db):
    async def scenario():
        from tests.game.fakes import ScriptedChatModel

        db = playthrough_db
        owner_id, run_id, hero_id = await _setup_run(db, username="investigation-flow")
        await playthrough_service.use_exit(
            db, user_id=owner_id, actor_id=hero_id, exit_id=TO_THORNWAY
        )

        saver = InMemorySaver(serde=checkpointer_service.checkpoint_serde())
        config = {"configurable": {"thread_id": run_id}}

        search_text = "I search the wool-marked narrow cut at ankle height for signs of passage."
        search_turn_id = generate_id()
        await playthrough_service.record_player_action(
            db, user_id=owner_id, run_id=run_id, text=search_text, turn_id=search_turn_id
        )
        frame = _frame(
            run_id=run_id,
            hero_id=hero_id,
            turn_id=search_turn_id,
            input_kind="action",
            text=search_text,
        )

        model = ScriptedChatModel(
            [
                AIMessage(content="Rosalind crouches over the low thorn."),
                ReadMoveOut(intent="search", refs={}, proposed=None),
                # `ASSESS_MOVE` (← sprint 011/08 fix): the scene's own
                # hidden fact is authored, not invented -- the model only
                # points at `evidence.secrets[0]`.
                MoveAssessmentOut(
                    applies=True,
                    dc=5,
                    dc_source="authored",
                    consequence_ids=[],
                    secret_index=0,
                    fixture_id=None,
                    check_action=None,
                ),
                "The widened cut confirms something heavy has passed this way more than once.",
            ]
        )
        flow_nodes.set_runtime(flow_nodes.FlowRuntime(db=db, user_id=owner_id, model=model))
        graph = build_graph(model=model, checkpointer=saver)

        result = await graph.ainvoke(initial_state(frame), config=config)
        interrupts = result["__interrupt__"]
        assert interrupts[0].value["ability"] == "wisdom"
        assert interrupts[0].value["skill"] == "Perception"
        assert interrupts[0].value["dc"] == 5

        awaiting_mid = await playthrough_service.get_awaiting(db, user_id=owner_id, run_id=run_id)
        assert awaiting_mid.startswith("roll:")
        request_id = awaiting_mid.split(":", 1)[1]

        # --- restart: a fresh compiled graph over the same saver --------
        graph_restarted = build_graph(model=model, checkpointer=saver)
        result = await graph_restarted.ainvoke(
            Command(resume={"acknowledged": True}), config=config
        )
        assert "__interrupt__" not in result

        rows = await _events_for_run(db, run_id)
        by_turn = [row for row in rows if row.turn_id == frame.turn_id]
        rolls_requested = [row for row in by_turn if row.type == "roll_requested"]
        rolls = [row for row in by_turn if row.type == "roll"]

        assert len(rolls_requested) == 1
        assert rolls_requested[0].id == request_id
        assert len(rolls) == 1, "the roll must be consumed exactly once"
        assert rolls[0].payload["requestId"] == request_id

        kinds = [row.type for row in by_turn]
        assert kinds.index("roll_requested") < kinds.index("roll")
        assert kinds.index("roll") < kinds.index("narration")

        awaiting = await playthrough_service.get_awaiting(db, user_id=owner_id, run_id=run_id)
        assert awaiting == "none"

    asyncio.run(scenario())


@pytest.mark.database
def test_movement_persists_scene_change_and_narrates_arrival(playthrough_db):
    async def scenario():
        from tests.game.fakes import ScriptedChatModel

        db = playthrough_db
        owner_id, run_id, hero_id = await _setup_run(db, username="movement-flow")

        saver = InMemorySaver(serde=checkpointer_service.checkpoint_serde())
        config = {"configurable": {"thread_id": run_id}}

        move_text = "I follow the cart track to the treeline."
        move_turn_id = generate_id()
        await playthrough_service.record_player_action(
            db, user_id=owner_id, run_id=run_id, text=move_text, turn_id=move_turn_id
        )
        frame = _frame(
            run_id=run_id,
            hero_id=hero_id,
            turn_id=move_turn_id,
            input_kind="action",
            text=move_text,
        )

        model = ScriptedChatModel(
            [
                AIMessage(content="Rosalind follows the cart track north."),
                ReadMoveOut(
                    intent="move",
                    refs={},
                    proposed=[
                        {
                            "kind": "use_exit",
                            "payload": {"actor_id": hero_id, "exit_id": TO_THORNWAY},
                        }
                    ],
                ),
                "The cart track narrows into the Thornway; the village falls behind you.",
            ]
        )
        flow_nodes.set_runtime(flow_nodes.FlowRuntime(db=db, user_id=owner_id, model=model))
        graph = build_graph(model=model, checkpointer=saver)
        result = await graph.ainvoke(initial_state(frame), config=config)
        assert "__interrupt__" not in result

        rows = await _events_for_run(db, run_id)
        by_turn = [row for row in rows if row.turn_id == frame.turn_id]
        kinds = [row.type for row in by_turn]
        assert "scene_entered" in kinds, kinds
        assert "narration" in kinds, kinds
        assert kinds.index("scene_entered") < kinds.index("narration")

        situation = await playthrough_service.get_situation(db, user_id=owner_id, run_id=run_id)
        assert situation.scene_id == THORNWAY

        awaiting = await playthrough_service.get_awaiting(db, user_id=owner_id, run_id=run_id)
        assert awaiting == "none"

    asyncio.run(scenario())


@pytest.mark.database
def test_combat_from_ambiguous_target_to_defeat(playthrough_db):
    async def scenario():
        from tests.game.fakes import ScriptedChatModel

        db = playthrough_db
        owner_id, run_id, hero_id = await _setup_run(db, username="combat-flow")
        await playthrough_service.use_exit(
            db, user_id=owner_id, actor_id=hero_id, exit_id=TO_THORNWAY
        )
        # `lair-maw`'s own exit's condition needs the wool-marked trail --
        # bypass it with a direct `interact`... simplest: the lair-maw
        # placement is only reachable once the hidden exit condition is
        # met, which this scenario does not need to exercise, so drop the
        # player straight into the scene with three goblins the way the
        # concurrent-rolls test does: two `use_exit` calls in a row, once
        # `to-lair-maw`'s own condition is authored as always reachable by
        # this campaign's fixture setup (← `test_concurrent_monster_rolls_
        # database.py`, the same path).
        await playthrough_service.use_exit(
            db, user_id=owner_id, actor_id=hero_id, exit_id="to-lair-maw"
        )

        goblin_ids = await _object_ids(db, run_id, template_id=GOBLIN_TEMPLATE, scene_id=LAIR_MAW)
        assert len(goblin_ids) >= 2, "greenhollow/v1's lair-maw placement changed under this test"

        knife_row = (
            await db.execute(
                text(
                    "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                    "AND owner_object_id = :hero_id AND template_id = 'shepherds-knife'"
                ),
                {"run_id": run_id, "hero_id": hero_id},
            )
        ).one()
        knife_id = knife_row.id

        saver = InMemorySaver(serde=checkpointer_service.checkpoint_serde())
        config = {"configurable": {"thread_id": run_id}}

        attack_text = "I attack one of the goblins with my knife."
        attack_turn_id = generate_id()
        await playthrough_service.record_player_action(
            db, user_id=owner_id, run_id=run_id, text=attack_text, turn_id=attack_turn_id
        )
        frame = _frame(
            run_id=run_id,
            hero_id=hero_id,
            turn_id=attack_turn_id,
            input_kind="action",
            text=attack_text,
        )

        script: list = [
            AIMessage(content="Rosalind squares up against the goblins."),
            ReadMoveOut(
                intent="attack",
                refs={"attack": "Shepherd's Knife", "item_id": knife_id},
                proposed=None,
            ),
            # judge_reference: several live candidates, none singled out by
            # the fiction -- ask.
            ReferenceJudgementOut(chosen_id=None, ask_choice=list(goblin_ids)),
        ]
        # Every eligible hostile gets exactly one `monster_action` decision
        # per round; up to `len(goblin_ids)` of them may be asked before the
        # hero goes down (`_FixedRng`'s own deterministic damage decides
        # how many actually get the chance).
        for target in goblin_ids:
            script.append(
                MonsterActionOut(actor_id=target, attack="Rusty Shortsword", target_id=hero_id)
            )
        script.append("The goblins press their attack and Rosalind falls.")

        model = ScriptedChatModel(script)
        flow_nodes.set_runtime(flow_nodes.FlowRuntime(db=db, user_id=owner_id, model=model))
        graph = build_graph(model=model, checkpointer=saver)

        result = await graph.ainvoke(initial_state(frame), config=config)

        # Resolve the ambiguous choice -- human-readable, numbered labels
        # (never a raw id, ← brief), privately mapped back to the goblins'
        # own ids by `operations._accept_choice`.
        expected_labels = [f"Goblin Raider ({i + 1})" for i in range(len(goblin_ids))]
        assert result["__interrupt__"][0].value["options"] == expected_labels
        chosen_label = expected_labels[0]
        result = await graph.ainvoke(Command(resume=chosen_label), config=config)

        # Settle initiative: a hero-side roll, then whichever side is
        # asked for a roll never interrupts twice in a row without this
        # file resuming it.
        guard = 0
        while "__interrupt__" in result:
            interrupt = result["__interrupt__"][0]
            guard += 1
            assert guard < 40, "runaway interrupt loop"
            if interrupt.value.get("options"):
                resume_value = interrupt.value["options"][0]
            else:
                resume_value = {"acknowledged": True}
            result = await graph.ainvoke(Command(resume=resume_value), config=config)

        rows = await _events_for_run(db, run_id)
        by_turn = [row for row in rows if row.turn_id == frame.turn_id]
        kinds = [row.type for row in by_turn]

        attacks = [
            row
            for row in by_turn
            if row.type == "tool_call" and row.payload.get("name") == "attack"
        ]
        damages = [
            row
            for row in by_turn
            if row.type == "tool_call" and row.payload.get("name") == "damage"
        ]
        hits = [row for row in attacks if row.payload["outcome"]["outcome"] in ("hit", "crit")]
        # Every hit this scenario produced has a matching damage applied
        # before turn closure -- a hit never closes without one.
        assert len(hits) >= 1, kinds
        assert len(damages) >= len(hits), kinds

        goblin_attacks = [
            row for row in attacks if row.payload["args"].get("actorId") in goblin_ids
        ]
        attacker_ids = [row.payload["args"]["actorId"] for row in goblin_attacks]
        # Each hostile that acted did so exactly once.
        assert len(attacker_ids) == len(set(attacker_ids)), attacker_ids
        assert attacker_ids, kinds

        run_row = (
            await db.execute(
                text("SELECT status FROM campaign_runs WHERE id = :run_id"),
                {"run_id": run_id},
            )
        ).one()
        assert run_row.status == "finished"

        system_rows = [row for row in by_turn if row.type == "system"]
        assert system_rows, kinds
        assert system_rows[-1].payload["details"]["outcome"] == "defeat", system_rows[-1].payload

        awaiting = await playthrough_service.get_awaiting(db, user_id=owner_id, run_id=run_id)
        assert awaiting == "none"

    asyncio.run(scenario())
