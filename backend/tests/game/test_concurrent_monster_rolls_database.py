"""Sprint 010/11 round 4, Fault A -- ← finding: two goblins acting in one
turn had the model emit two `roll_dice` tool calls in the same `AIMessage`.
LangGraph's `ToolNode` runs a batch of tool calls concurrently
(`asyncio.gather`), and both calls shared the turn's one `AsyncSession` --
not safe for concurrent use. Live play showed a dangling `roll_requested`
with no matching `roll` (and a SQLAlchemy warning at `append_event`'s own
`db.add()`, which `pyproject.toml`'s `filterwarnings = ["error"]` turns
into an outright failure here if the race reappears).

Drives the real compiled graph (`game.service.build_agent`) against a real
scratch database with two goblins already placed by ordinary mechanics
(`start_campaign_run` / `create_character` / `enter_adventure` /
`use_exit`, the same path `tests/playthrough/test_acceptance_fight_in_the_
transcript.py` walks), and a scripted model stand-in -- no real model call
anywhere in this file (`ainvoke_chat` only ever calls this stand-in's own
`ainvoke`, never a network seam)."""

import asyncio

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import text

from app.core.ids import generate_id
from app.core.llm import service as llm_service
from app.modules.game import service as game_service
from app.modules.game.agent.state import DmContext

CAMPAIGN_ID = "greenhollow"
VILLAGE_GREEN = "village-green"
TO_THORNWAY = "to-thornway"
TO_LAIR_MAW = "to-lair-maw"
LAIR_MAW = "lair-maw"
GOBLIN_TEMPLATE = "goblin"

EMBEDDING_WIDTH = 1536


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


async def _goblin_ids(session, run_id: str) -> list[str]:
    rows = (
        await session.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = :template_id AND scene_id = :scene_id ORDER BY id"
            ),
            {"run_id": run_id, "template_id": GOBLIN_TEMPLATE, "scene_id": LAIR_MAW},
        )
    ).all()
    return [row.id for row in rows]


async def _events_for_turn(session, run_id: str, turn_id: str) -> list:
    rows = (
        await session.execute(
            text(
                "SELECT id, type, payload FROM events WHERE campaign_run_id = :run_id "
                "AND turn_id = :turn_id ORDER BY id"
            ),
            {"run_id": run_id, "turn_id": turn_id},
        )
    ).all()
    return rows


class _ScriptedCallModel:
    """`bind_tools()` is a no-op: the script already carries any tool
    calls. Each `.ainvoke()` consumes the next scripted item -- the same
    stand-in `tests/game/test_narrate_seam.py` uses."""

    def __init__(self, script: list) -> None:
        self._script = list(script)

    def bind_tools(self, tools, **kwargs):
        return self

    async def ainvoke(self, prompt):
        return self._script.pop(0)


@pytest.mark.database
def test_two_goblin_rolls_in_one_batch_leave_no_dangling_request(playthrough_db, monkeypatch):
    monkeypatch.setattr(
        llm_service,
        "embed_texts",
        lambda texts, *, model=None: llm_service.EmbeddingResult(
            vectors=[[0.0] * EMBEDDING_WIDTH for _ in texts],
            usage=llm_service.Usage(
                prompt_tokens=0, completion_tokens=0, total_tokens=0, cost_usd=None
            ),
        ),
    )

    async def scenario():
        db = playthrough_db
        owner_id = generate_id()
        await _insert_user(db, owner_id, username="two-goblins")
        await db.commit()

        run = await game_service.playthrough_service.start_campaign_run(
            db, user_id=owner_id, campaign_id=CAMPAIGN_ID
        )
        character = await game_service.playthrough_service.create_character(
            db, user_id=owner_id, run_id=run.id
        )
        await game_service.playthrough_service.enter_adventure(db, user_id=owner_id, run_id=run.id)
        await game_service.playthrough_service.use_exit(
            db, user_id=owner_id, actor_id=character.id, exit_id=TO_THORNWAY
        )
        await game_service.playthrough_service.use_exit(
            db, user_id=owner_id, actor_id=character.id, exit_id=TO_LAIR_MAW
        )

        goblin_ids = await _goblin_ids(db, run.id)
        assert len(goblin_ids) >= 2, "greenhollow/v1's lair-maw placement changed under this test"
        goblin_a, goblin_b = goblin_ids[0], goblin_ids[1]

        # Two `roll_dice` tool calls in the *same* AIMessage -- ToolNode's
        # own `asyncio.gather` batch, the shape live play produced when two
        # goblins acted in one turn.
        two_rolls = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call-a",
                    "name": "roll_dice",
                    "args": {
                        "kind": "attack",
                        "context": {"attack": "Rusty Shortsword"},
                        "actor_id": goblin_a,
                    },
                },
                {
                    "id": "call-b",
                    "name": "roll_dice",
                    "args": {
                        "kind": "attack",
                        "context": {"attack": "Rusty Shortsword"},
                        "actor_id": goblin_b,
                    },
                },
            ],
        )
        final_narration = AIMessage(content="Two goblins swing their shortswords at you!")

        model = _ScriptedCallModel([two_rolls, final_narration])
        agent = game_service.build_agent(model=model, checkpointer=InMemorySaver())

        turn_id = generate_id()
        ctx = DmContext(
            db=db, user_id=owner_id, actor_id=character.id, run_id=run.id, turn_id=turn_id
        )
        await game_service.turn(
            agent, thread_id=run.id, context=ctx, player_text="Let the goblins attack."
        )

        rows = await _events_for_turn(db, run.id, turn_id)
        rolls_requested = [r for r in rows if r.type == "roll_requested"]
        rolls = [r for r in rows if r.type == "roll"]

        assert len(rolls_requested) == 2, [dict(r._mapping) for r in rows]
        assert len(rolls) == 2, [dict(r._mapping) for r in rows]

        requested_ids = {r.id for r in rolls_requested}
        answered_ids = {r.payload["requestId"] for r in rolls}
        assert answered_ids == requested_ids, "every roll_requested must have exactly one roll"

        requested_actors = {r.payload["actorId"] for r in rolls_requested}
        assert requested_actors == {goblin_a, goblin_b}

        awaiting = await game_service.playthrough_service.get_awaiting(
            db, user_id=owner_id, run_id=run.id
        )
        assert awaiting == "none"

    asyncio.run(scenario())
