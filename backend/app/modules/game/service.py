"""`game` is the agent layer: it decides, narrates and calls tools. Every
mechanic belongs to `playthrough.service`; nothing here rolls a die or
writes an event.

The model comes from `core/llm/service.chat_model()` so the API-key check
and `max_retries=0` stay in one place. The checkpointer defaults to
`InMemorySaver()` when omitted (e.g. for lightweight testing), or an
`AsyncPostgresSaver` in persistent sessions.

`run_turn` (sprint 010/03) is the one entry point a route calls: it opens
its own checkpointer connection, reads the DM thread's own state back
(`thread_state`) and decides which of five kinds this turn is from that
state and the transcript alone -- never from what the caller claims.

Tests monkeypatch `service.chat_model` and `service.load_prompt`.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.checkpointer import service as checkpointer_service
from app.core.ids import generate_id
from app.core.llm.service import chat_model
from app.core.prompts.service import load_prompt
from app.core.tracing import service as tracing
from app.modules.game.agent.graph import build_graph
from app.modules.game.agent.state import DmContext, DmState, rolls_in
from app.modules.game.errors import ActionNotAvailableError
from app.modules.playthrough import service as playthrough_service

SYSTEM_PROMPT_ID = "game/system/dm"

TurnKind = Literal["answer", "roll", "retry", "action", "opening"]


@dataclass(frozen=True)
class TurnResult:
    reply: str
    rolls: list[dict[str, Any]] = field(default_factory=list)
    interrupt: dict[str, Any] | None = None


@dataclass(frozen=True)
class ThreadState:
    interrupt: dict[str, Any] | None
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
    prompt_version: str | None = None,
) -> CompiledStateGraph[DmState, DmContext]:
    return build_graph(
        model if model is not None else chat_model(),
        system_prompt=load_prompt(SYSTEM_PROMPT_ID, version=prompt_version).text,
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver(),
    )


def _extract_turn_result(result: dict[str, Any], before_count: int) -> TurnResult:
    interrupt_info = None
    if "__interrupt__" in result and result["__interrupt__"]:
        interrupt_info = result["__interrupt__"][0].value
    messages = result.get("messages", [])
    reply = messages[-1].text if messages and hasattr(messages[-1], "text") else ""
    return TurnResult(
        reply=reply,
        rolls=rolls_in(messages, start=before_count),
        interrupt=interrupt_info,
    )


def _turn_config(*, thread_id: str, context: DmContext) -> RunnableConfig:
    metadata = {
        "thread_id": thread_id,
        "user_id": context.user_id,
        "agent": "dungeon-master",
    }
    if context.run_id is not None:
        metadata["campaign_id"] = context.run_id
    if context.turn_id is not None:
        metadata["turn_id"] = context.turn_id
    return RunnableConfig(
        **tracing.langchain_config("dm-turn", metadata=metadata),
        configurable={"thread_id": thread_id},
        tags=["agent:dm"],
    )


async def turn(
    agent: CompiledStateGraph[DmState, DmContext],
    *,
    thread_id: str,
    context: DmContext,
    player_text: str,
) -> TurnResult:
    """`rolls` covers this turn only, hence the message count taken before
    invoking."""
    config = _turn_config(thread_id=thread_id, context=context)
    before = (await agent.aget_state(config)).values.get("messages", [])
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=player_text)]}, config=config, context=context
    )
    return _extract_turn_result(result, len(before))


async def resume(
    agent: CompiledStateGraph[DmState, DmContext],
    *,
    thread_id: str,
    context: DmContext,
    resume_value: Any,
) -> TurnResult:
    """Resumes a paused agent thread from an interrupt."""
    config = _turn_config(thread_id=thread_id, context=context)
    before = (await agent.aget_state(config)).values.get("messages", [])
    result = await agent.ainvoke(Command(resume=resume_value), config=config, context=context)
    return _extract_turn_result(result, len(before))


async def retry(
    agent: CompiledStateGraph[DmState, DmContext],
    *,
    thread_id: str,
    context: DmContext,
) -> TurnResult:
    """Resumes a turn that broke off mid-flight: `invoke(None)` continues
    the graph from its last saved checkpoint step, rather than feeding it a
    new human message (`turn`) or answering an interrupt (`resume`) --
    whatever step already completed (a roll already recorded, say) is not
    repeated, only whatever comes after it (sprint 010/03, I3)."""
    config = _turn_config(thread_id=thread_id, context=context)
    before = (await agent.aget_state(config)).values.get("messages", [])
    result = await agent.ainvoke(None, config=config, context=context)
    return _extract_turn_result(result, len(before))


async def thread_state(
    agent: CompiledStateGraph[DmState, DmContext], *, thread_id: str
) -> ThreadState:
    """The DM thread's own state, read back from the checkpointer alone --
    never inferred from what a caller claims (sprint 010/03, I3).

    `interrupt` is the value of whichever `question` or `roll_request`
    interrupt is pending on this thread's current step, or `None` when
    nothing is pending -- the same shape `turn`/`resume` already surface on
    `TurnResult.interrupt`, read here straight from the checkpoint instead
    of a fresh invoke. `pending` is whether the graph has a next step
    queued at all, interrupted or not; `run_turn` only consults it once
    `interrupt` is already `None`, so `pending` alone then means a turn
    that broke off mid-flight with nothing waiting on the player.
    """
    config = RunnableConfig(configurable={"thread_id": thread_id})
    snapshot = await agent.aget_state(config)
    interrupt_value = None
    if snapshot.tasks and snapshot.tasks[0].interrupts:
        interrupt_value = snapshot.tasks[0].interrupts[0].value
    return ThreadState(interrupt=interrupt_value, pending=bool(snapshot.next))


async def run_turn(
    db: AsyncSession,
    *,
    user_id: str,
    run_id: str,
    text: str | None,
) -> TurnOutcome:
    """Runs one turn for `run_id`, deciding for itself which of five kinds
    the turn is from the DM thread's own checkpoint state plus the
    transcript -- never from `text` alone (sprint 010/03, I2).

    `playthrough_service.get_member_character` gates membership first (a
    caller not seated at the run raises `CampaignRunNotFoundError` here,
    before a checkpointer connection is even opened) and supplies the
    acting hero's id, exactly the way the terminal command already
    resolves it. The DM's memory thread is the run id itself (sprints
    010/01-02).

    In order:
    1. A pending `question` interrupt -> kind `answer`. `text` must equal
       one of the interrupt's own `options`, or may be anything when
       `options` is empty; otherwise `ActionNotAvailableError` (no write,
       no resume). Accepted, a `player_action` event
       (`{text, answersQuestionId}`) is appended under the *open* turn's id
       and committed before `resume(text)` -- the fix for the finding that
       nothing else ever writes a `player_action` on an answered question,
       which would otherwise leave `get_awaiting` reporting the same
       question forever.
    2. A pending `roll_request` interrupt -> kind `roll`. `resume({"action":
       "roll"})` -- `text` is discarded; the server rolls, never the
       caller's own number.
    3. No interrupt but the graph still has a next step queued -> kind
       `retry`: `invoke(None)` resumes from the last saved step, repeating
       nothing already recorded.
    4. `text` present -> kind `action`, a newly minted turn id.
    5. No `text` -> kind `opening`, DM-led: `record_action=False` on the
       context stops `record_action` (`agent/nodes.py`) from writing a
       player row for it.

    Kinds 1-3 reuse the open turn's own id (`playthrough_service.
    open_turn_id`) rather than minting a new one -- except when there is
    none to reuse (`open_turn_id` returns `None`: the leg that broke had
    written no event yet, e.g. an opening turn that crashed before its
    first narration), in which case a fresh one is minted the same way
    kinds 4-5 always do (`core.ids.generate_id`, the same ULID every other
    id in this app is) and the resumed leg continues under it -- never
    left `None`, which would fail `TurnOutcome.turn_id: str` downstream.
    `awaiting` on the returned `TurnOutcome` is `get_awaiting` read *after*
    the turn runs, so it always reflects whatever the turn just did, not
    what it started from.
    """
    character = await playthrough_service.get_member_character(db, user_id=user_id, run_id=run_id)

    async with checkpointer_service.checkpointer() as saver:
        agent = build_agent(checkpointer=saver)
        snapshot = await thread_state(agent, thread_id=run_id)

        kind: TurnKind
        if snapshot.interrupt is not None:
            interrupt_type = snapshot.interrupt.get("type")
            if interrupt_type == "question":
                kind = "answer"
                options = snapshot.interrupt.get("options") or []
                if options and text not in options:
                    awaiting = await playthrough_service.get_awaiting(
                        db, user_id=user_id, run_id=run_id
                    )
                    raise ActionNotAvailableError(awaiting=awaiting, options=options)

                turn_id = (
                    await playthrough_service.open_turn_id(db, user_id=user_id, run_id=run_id)
                    or generate_id()
                )
                await playthrough_service.append_event(
                    db,
                    run_id=run_id,
                    type="player_action",
                    visibility="player",
                    payload={
                        "text": text or "",
                        "answersQuestionId": snapshot.interrupt.get("question_id"),
                    },
                    turn_id=turn_id,
                )
                await db.commit()

                context = DmContext(
                    db=db, user_id=user_id, actor_id=character.id, run_id=run_id, turn_id=turn_id
                )
                await resume(agent, thread_id=run_id, context=context, resume_value=text)
            elif interrupt_type == "roll_request":
                kind = "roll"
                turn_id = (
                    await playthrough_service.open_turn_id(db, user_id=user_id, run_id=run_id)
                    or generate_id()
                )
                context = DmContext(
                    db=db, user_id=user_id, actor_id=character.id, run_id=run_id, turn_id=turn_id
                )
                await resume(
                    agent, thread_id=run_id, context=context, resume_value={"action": "roll"}
                )
            else:  # pragma: no cover - only `ask_player`/`request_player_roll` interrupt
                raise AssertionError(f"unknown interrupt type: {interrupt_type!r}")
        elif snapshot.pending:
            kind = "retry"
            turn_id = (
                await playthrough_service.open_turn_id(db, user_id=user_id, run_id=run_id)
                or generate_id()
            )
            context = DmContext(
                db=db, user_id=user_id, actor_id=character.id, run_id=run_id, turn_id=turn_id
            )
            await retry(agent, thread_id=run_id, context=context)
        elif text and text.strip():
            kind = "action"
            turn_id = generate_id()
            context = DmContext(
                db=db, user_id=user_id, actor_id=character.id, run_id=run_id, turn_id=turn_id
            )
            await turn(agent, thread_id=run_id, context=context, player_text=text)
        else:
            # No real interrupt is pending and nothing is queued to retry
            # -- the graph itself is not waiting on anything. A non-`"none"`
            # `awaiting` here (sprint 010/11 round 4, Fault A -- ← finding)
            # therefore names a *stale* request, never the player's own: a
            # monster's own roll never reaches here (`get_awaiting` already
            # excludes it), but an old row written before that fix, or a
            # question nothing ever answered, still could. Refuse rather
            # than silently writing a DM-led filler turn for it -- exactly
            # the bad-option refusal the `answer` branch above already
            # makes, reused here for the same "no write, no resume" shape.
            pending_awaiting = await playthrough_service.get_awaiting(
                db, user_id=user_id, run_id=run_id
            )
            if pending_awaiting != "none":
                raise ActionNotAvailableError(awaiting=pending_awaiting, options=[])

            kind = "opening"
            turn_id = generate_id()
            context = DmContext(
                db=db,
                user_id=user_id,
                actor_id=character.id,
                run_id=run_id,
                turn_id=turn_id,
                record_action=False,
            )
            await turn(agent, thread_id=run_id, context=context, player_text=text or "")

    awaiting = await playthrough_service.get_awaiting(db, user_id=user_id, run_id=run_id)
    return TurnOutcome(turn_id=turn_id, kind=kind, awaiting=awaiting)
