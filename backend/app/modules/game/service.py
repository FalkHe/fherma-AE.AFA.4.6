"""`game` is the agent layer: it decides, narrates and calls tools. Every
mechanic belongs to `playthrough.service`; nothing here rolls a die or
writes an event.

The model comes from `core/llm/service.chat_model()` so the API-key check
and `max_retries=0` stay in one place. The checkpointer defaults to
`InMemorySaver()` when omitted (e.g. for lightweight testing), or an
`AsyncPostgresSaver` in persistent sessions.

`run_turn` is the one entry point a route calls. It runs every turn through
the five-node flow in `agent/graph.py`. The turn's kind is read from the
DM thread's own checkpoint: `AwaitingRef` means a roll or choice resume,
`snapshot.next` means a retry, and otherwise the input starts an action or
opening. The checkpoint is authoritative; transcript history is only read
back for the response after graph execution.

Tests monkeypatch `service.chat_model` and the compiled graph's
`ainvoke`/`aget_state`.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.checkpointer import service as checkpointer_service
from app.core.ids import generate_id
from app.core.llm.service import chat_model
from app.modules.game.agent import flow_nodes
from app.modules.game.agent.flow_state import AwaitingRef, TurnFrame
from app.modules.game.agent.graph import build_graph, initial_state
from app.modules.game.errors import ActionNotAvailableError
from app.modules.playthrough import service as playthrough_service

TurnKind = Literal["answer", "roll", "retry", "action", "opening"]


@dataclass(frozen=True)
class TurnResult:
    """CLI-only rendering shape (`game/commands.py`) -- narration text plus
    the rolls made during one turn segment, assembled from the transcript
    events `run_turn` just wrote, never from a graph return value."""

    reply: str
    rolls: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ThreadState:
    """The DM thread's own checkpointed state, read back without ever
    invoking the graph -- `awaiting` is `None` when nothing is pending,
    `pending` is whether the graph has a next step queued at all
    (interrupted or not)."""

    awaiting: AwaitingRef | None
    pending: bool


@dataclass(frozen=True)
class TurnOutcome:
    turn_id: str
    kind: TurnKind
    awaiting: str


def build_agent(
    *,
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    return build_graph(
        model if model is not None else chat_model(),
        checkpointer=(
            checkpointer
            if checkpointer is not None
            else InMemorySaver(serde=checkpointer_service.checkpoint_serde())
        ),
    )


async def thread_state(agent: CompiledStateGraph, *, thread_id: str) -> ThreadState:
    """Reads `run_id`'s own checkpoint back (sprint 011/08, WI2, I2):
    `awaiting` straight off `state["awaiting"]`, `pending` off whether the
    graph has a next step queued -- never off an old-style interrupt
    payload, which the new flow no longer produces."""
    config = RunnableConfig(configurable={"thread_id": thread_id})
    snapshot = await agent.aget_state(config)
    awaiting = snapshot.values.get("awaiting") if snapshot.values else None
    return ThreadState(awaiting=awaiting, pending=bool(snapshot.next))


async def run_turn(
    db: AsyncSession,
    *,
    user_id: str,
    run_id: str,
    text: str | None,
) -> TurnOutcome:
    """Runs one turn for `run_id` through the new five-node flow, deciding
    for itself which of five kinds this turn is from the DM thread's own
    checkpoint alone -- never from `text` alone (sprint 011/08, WI2, I2).

    `playthrough_service.get_member_character` gates membership first (a
    caller not seated at the run raises `CampaignRunNotFoundError` here,
    before a checkpointer connection is even opened) and supplies the
    acting hero's id. The DM's memory thread is the run id itself.

    In order:
    1. `state["awaiting"].kind == "roll"` -> kind `roll`. Resumed with
       `Command(resume={"acknowledged": True})` -- the server rolls, never
       a caller-sent number; the payload must be non-empty (← round 2
       finding: an empty dict is read as a resume-by-interrupt-id map by
       langgraph 1.2.11, not a value, so it never resumes at all).
    2. `state["awaiting"].kind == "choice"` -> kind `answer`. `text` must
       equal one of the checkpointed public `options`, or may be anything
       when `options` is empty; otherwise `ActionNotAvailableError` (no
       resume). Resumed with `Command(resume=text)`.
    3. No `awaiting` but `snapshot.next` is non-empty -> kind `retry`:
       `ainvoke(None)` resumes from the last saved step, repeating nothing
       already recorded.
    4. `text` present -> kind `action`: a newly minted turn id,
       `playthrough_service.record_player_action` first, then
       `ainvoke(initial_state(...))`.
    5. No `text` -> kind `opening`, DM-led: no player row is written.

    Neither the `roll` nor `answer` branch writes an answer/roll row here
    -- the flow's own `accept_choice`/`roll_player` operations write those
    (two-row form) once the resumed graph reaches them. `awaiting` on the
    returned `TurnOutcome` is `playthrough_service.get_awaiting` read
    *after* the turn runs, so it always reflects whatever the turn just
    did, not what it started from.
    """
    character = await playthrough_service.get_member_character(db, user_id=user_id, run_id=run_id)
    model = chat_model()

    async with checkpointer_service.checkpointer() as saver:
        agent = build_agent(model=model, checkpointer=saver)
        flow_nodes.set_runtime(flow_nodes.FlowRuntime(db=db, user_id=user_id, model=model))

        config = RunnableConfig(configurable={"thread_id": run_id})
        snapshot = await agent.aget_state(config)
        awaiting: AwaitingRef | None = snapshot.values.get("awaiting") if snapshot.values else None

        async def _resolved_turn_id() -> str:
            turn = snapshot.values.get("turn") if snapshot.values else None
            if turn is not None:
                return turn.turn_id
            return (
                await playthrough_service.open_turn_id(db, user_id=user_id, run_id=run_id)
                or generate_id()
            )

        kind: TurnKind
        if awaiting is not None and awaiting.kind == "roll":
            kind = "roll"
            turn_id = await _resolved_turn_id()
            # ← round 2 finding: `Command(resume={})` -- an *empty* dict --
            # is read by langgraph 1.2.11 as a resume-by-interrupt-id map,
            # not a value for the one pending interrupt, so it never
            # actually resumes (200 returned, no event written, the thread
            # stays at `next=('await_player',)`). A non-empty acknowledgement
            # is required; `{"acknowledged": True}` matches what
            # `advance.resume_operation`/the scenario tests already send.
            await agent.ainvoke(Command(resume={"acknowledged": True}), config=config)
        elif awaiting is not None:
            kind = "answer"
            options = awaiting.public.get("options") or []
            if options and text not in options:
                current_awaiting = await playthrough_service.get_awaiting(
                    db, user_id=user_id, run_id=run_id
                )
                raise ActionNotAvailableError(awaiting=current_awaiting, options=list(options))
            turn_id = await _resolved_turn_id()
            await agent.ainvoke(Command(resume=text), config=config)
        elif snapshot.next:
            kind = "retry"
            turn_id = await _resolved_turn_id()
            await agent.ainvoke(None, config=config)
        else:
            if text and text.strip():
                kind = "action"
                turn_id = generate_id()
                await playthrough_service.record_player_action(
                    db, user_id=user_id, run_id=run_id, text=text, turn_id=turn_id
                )
                frame = TurnFrame(
                    run_id=run_id,
                    hero_id=character.id,
                    turn_id=turn_id,
                    input_kind="action",
                    text=text,
                    status="open",
                    round_admitted=False,
                )
                await agent.ainvoke(initial_state(frame), config=config)
            else:
                kind = "opening"
                turn_id = generate_id()
                frame = TurnFrame(
                    run_id=run_id,
                    hero_id=character.id,
                    turn_id=turn_id,
                    input_kind="opening",
                    text=None,
                    status="open",
                    round_admitted=False,
                )
                await agent.ainvoke(initial_state(frame), config=config)

    awaiting_str = await playthrough_service.get_awaiting(db, user_id=user_id, run_id=run_id)
    return TurnOutcome(turn_id=turn_id, kind=kind, awaiting=awaiting_str)
