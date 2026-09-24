"""The decision registry for the new flow (sprint 011/06, WI1): one call
into a model per `DecisionKind`, each rendering its own evidence into its
own prompt, validated against the situation before it is trusted, never
carrying an operation id, a die result or a graph destination out of the
model's own mouth.

`decide()` is the only entry point. A strategy that `binds_tools` runs a
plain, bounded tool loop (no graph) over exactly two read-only tools --
`lookup_rule` and `recall_history` -- capped at `MAX_TOOL_CALLS` total
calls, then always asks the model for its structured answer through
`with_structured_output(..., include_raw=True)` so usage can still be read
off the raw message underneath the parsed value. A structurally valid
answer that names something the situation does not recognise -- an
unknown operation kind, an operation kind the strategy does not allow, or
a stale id/attack/choice (`operations.validate_refs`) -- is re-prompted
with the reason under the same `decision_id`, at most `RETRY_BUDGET`
times, before `DecisionInvalid` escapes to the caller.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.prompts.service import load_prompt
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.situation import Situation
from app.modules.srd import service as srd_service
from app.modules.srd.errors import SrdCorpusEmptyError

from . import model_call
from .flow_state import GameFlowState, Operation, OperationKind, OperationSpec, ReactionSpec, Usage
from .operations import validate_refs

MAX_TOOL_CALLS = 3
RETRY_BUDGET = 2


class DecisionInvalid(Exception):
    """A model's answer stayed invalid after `RETRY_BUDGET` re-prompts."""


class DecisionKind(StrEnum):
    READ_MOVE = "read_move"
    INTERPRET_EVIDENCE = "interpret_evidence"
    JUDGE_REFERENCE = "judge_reference"
    ASSESS_MOVE = "assess_move"
    MONSTER_ACTION = "monster_action"
    WORLD_REACTION = "world_reaction"


@dataclass(frozen=True)
class DecisionRequest:
    decision_id: str
    kind: DecisionKind
    evidence_ids: tuple[str, ...]
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class DecisionResult:
    decision_id: str
    kind: DecisionKind
    value: Any
    usage: Usage


@dataclass(frozen=True)
class ReadMoveDecision:
    intent: str
    refs: Mapping[str, str]
    proposed: tuple[OperationSpec, ...] | None


@dataclass(frozen=True)
class EvidenceReading:
    summary: str
    supports: tuple[str, ...]


@dataclass(frozen=True)
class ReferenceJudgement:
    chosen_id: str | None
    ask_choice: tuple[str, ...]


@dataclass(frozen=True)
class MoveAssessment:
    applies: bool
    dc: int | None
    dc_source: Literal["authored", "rules"] | None
    consequence_ids: tuple[str, ...]


@dataclass(frozen=True)
class MonsterAction:
    actor_id: str
    attack: str
    target_id: str


@dataclass(frozen=True)
class WorldReaction:
    reactions: tuple[ReactionSpec, ...]


@dataclass(frozen=True)
class DecisionContext:
    db: AsyncSession
    user_id: str
    run_id: str
    hero_id: str
    situation: Situation
    model: BaseChatModel


## Pydantic output schemas -- the one place this module allows Pydantic,
## since these are what `with_structured_output` needs (← research).


class OperationSpecOut(BaseModel):
    kind: str
    payload: dict[str, Any] = {}


class ReadMoveOut(BaseModel):
    intent: str
    refs: dict[str, str] = {}
    proposed: list[OperationSpecOut] | None = None


class EvidenceReadingOut(BaseModel):
    summary: str
    supports: list[str] = []


class ReferenceJudgementOut(BaseModel):
    chosen_id: str | None = None
    ask_choice: list[str] = []


class MoveAssessmentOut(BaseModel):
    applies: bool
    dc: int | None = None
    dc_source: Literal["authored", "rules"] | None = None
    consequence_ids: list[str] = []


class MonsterActionOut(BaseModel):
    actor_id: str
    attack: str
    target_id: str


class ReactionSpecOut(BaseModel):
    reaction_id: str
    kind: str
    payload: dict[str, Any] = {}


class WorldReactionOut(BaseModel):
    reactions: list[ReactionSpecOut] = []


@dataclass(frozen=True)
class Strategy:
    prompt_key: str
    output_schema: type[BaseModel]
    allowed_operations: frozenset[OperationKind]
    binds_tools: bool
    evidence: Callable[[Situation, GameFlowState], Any]
    build: Callable[[Any, Situation], Any]


def _serialize(value: Any) -> Any:
    """A JSON-safe view of a frozen dataclass tree (`Situation` or
    `SituationPublic`, either one), recursively -- the only shape the
    evidence views ever are."""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _serialize(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _public_evidence(situation: Situation, state: GameFlowState) -> Any:
    return _serialize(situation.public())


def _private_evidence(situation: Situation, state: GameFlowState) -> Any:
    return _serialize(situation)


def _build_read_move(parsed: ReadMoveOut, situation: Situation) -> ReadMoveDecision:
    proposed = None
    if parsed.proposed is not None:
        proposed = tuple(
            OperationSpec(kind=OperationKind(op.kind), payload=dict(op.payload))
            for op in parsed.proposed
        )
    return ReadMoveDecision(intent=parsed.intent, refs=dict(parsed.refs), proposed=proposed)


def _build_evidence_reading(parsed: EvidenceReadingOut, situation: Situation) -> EvidenceReading:
    return EvidenceReading(summary=parsed.summary, supports=tuple(parsed.supports))


def _build_reference_judgement(
    parsed: ReferenceJudgementOut, situation: Situation
) -> ReferenceJudgement:
    return ReferenceJudgement(chosen_id=parsed.chosen_id, ask_choice=tuple(parsed.ask_choice))


def _build_move_assessment(parsed: MoveAssessmentOut, situation: Situation) -> MoveAssessment:
    return MoveAssessment(
        applies=parsed.applies,
        dc=parsed.dc,
        dc_source=parsed.dc_source,
        consequence_ids=tuple(parsed.consequence_ids),
    )


def _build_monster_action(parsed: MonsterActionOut, situation: Situation) -> MonsterAction:
    return MonsterAction(actor_id=parsed.actor_id, attack=parsed.attack, target_id=parsed.target_id)


def _build_world_reaction(parsed: WorldReactionOut, situation: Situation) -> WorldReaction:
    reactions = tuple(
        ReactionSpec(reaction_id=r.reaction_id, kind=r.kind, payload=dict(r.payload))
        for r in parsed.reactions
    )
    return WorldReaction(reactions=reactions)


DECISION_HANDLERS: dict[DecisionKind, Strategy] = {
    DecisionKind.READ_MOVE: Strategy(
        prompt_key="read-move",
        output_schema=ReadMoveOut,
        allowed_operations=frozenset(
            {
                OperationKind.INTERACT,
                OperationKind.TAKE_ITEM,
                OperationKind.DROP_ITEM,
                OperationKind.GIVE_ITEM,
                OperationKind.USE_EXIT,
                OperationKind.REQUEST_ROLL,
                OperationKind.REQUEST_CHOICE,
                OperationKind.SET_HOSTILITY,
                OperationKind.LEAVE_SCENE,
                OperationKind.ENTER_NEXT_ADVENTURE,
            }
        ),
        binds_tools=True,
        evidence=_public_evidence,
        build=_build_read_move,
    ),
    DecisionKind.INTERPRET_EVIDENCE: Strategy(
        prompt_key="interpret-evidence",
        output_schema=EvidenceReadingOut,
        allowed_operations=frozenset(),
        binds_tools=True,
        evidence=_public_evidence,
        build=_build_evidence_reading,
    ),
    DecisionKind.JUDGE_REFERENCE: Strategy(
        prompt_key="judge-reference",
        output_schema=ReferenceJudgementOut,
        allowed_operations=frozenset(),
        binds_tools=False,
        evidence=_public_evidence,
        build=_build_reference_judgement,
    ),
    DecisionKind.ASSESS_MOVE: Strategy(
        prompt_key="assess-move",
        output_schema=MoveAssessmentOut,
        allowed_operations=frozenset(),
        binds_tools=False,
        evidence=_private_evidence,
        build=_build_move_assessment,
    ),
    DecisionKind.MONSTER_ACTION: Strategy(
        prompt_key="monster-action",
        output_schema=MonsterActionOut,
        allowed_operations=frozenset({OperationKind.RESOLVE_ATTACK}),
        binds_tools=False,
        evidence=_public_evidence,
        build=_build_monster_action,
    ),
    DecisionKind.WORLD_REACTION: Strategy(
        prompt_key="world-reaction",
        output_schema=WorldReactionOut,
        allowed_operations=frozenset({OperationKind.SET_HOSTILITY, OperationKind.LEAVE_SCENE}),
        binds_tools=False,
        evidence=_private_evidence,
        build=_build_world_reaction,
    ),
}


def _build_tools(ctx: DecisionContext) -> list[Any]:
    """The two read-only tools a `binds_tools` strategy may call -- fresh
    closures over `ctx` every `decide()` call, since `ctx.db`/`run_id`
    differ per call and a `@tool`-decorated module-level function cannot
    close over either."""

    @tool
    async def lookup_rule(query: str, limit: int = 5) -> dict[str, Any]:
        """Search official D&D 5e SRD rules, spells, combat mechanics, and
        conditions. `query` is the rules question or keyword. `limit` is
        the maximum number of matching rule passages to return."""
        try:
            matches = await srd_service.search_rules(ctx.db, query=query, limit=limit)
        except SrdCorpusEmptyError:
            return {"status": "ok", "query": query, "rules": []}
        return {
            "status": "ok",
            "query": query,
            "rules": [{"heading": m.heading_path, "text": m.text} for m in matches],
        }

    @tool
    async def recall_history(query: str, limit: int = 3) -> dict[str, Any]:
        """Search past narration and story memories from anywhere in the
        campaign by semantic meaning, each expanded to its own turn.
        `query` is the search phrase. `limit` is the maximum number of
        matches to return."""
        turns = await playthrough_service.recall_history(
            ctx.db, user_id=ctx.user_id, run_id=ctx.run_id, query=query, limit=limit
        )
        return {
            "status": "ok",
            "query": query,
            "turns": [
                {
                    "turn_id": turn.turn_id,
                    "anchor_event_id": turn.anchor_event_id,
                    "events": [
                        {
                            "id": event.id,
                            "type": event.type,
                            "payload": event.payload,
                            "created_at": event.created_at.isoformat(),
                        }
                        for event in turn.events
                    ],
                }
                for turn in turns
            ],
        }

    return [lookup_rule, recall_history]


async def _run_tool_loop(
    ctx: DecisionContext, model: BaseChatModel, messages: list[Any], *, label: str
) -> list[AIMessage]:
    """Appends to `messages` in place; returns every `AIMessage` produced,
    for usage accounting. Stops once `MAX_TOOL_CALLS` tool calls have run
    in total (not turns), or once a reply carries no tool call."""
    tools_by_name = {t.name: t for t in _build_tools(ctx)}
    bound = model.bind_tools(list(tools_by_name.values()))
    ai_messages: list[AIMessage] = []
    tool_calls_made = 0
    while tool_calls_made < MAX_TOOL_CALLS:
        ai_message = await model_call.ainvoke(bound, messages, label=label)
        ai_messages.append(ai_message)
        messages.append(ai_message)
        if not ai_message.tool_calls:
            break
        for call in ai_message.tool_calls:
            if tool_calls_made >= MAX_TOOL_CALLS:
                break
            tool_fn = tools_by_name.get(call["name"])
            if tool_fn is None:
                result: Any = {"status": "error", "message": "unknown_tool"}
            else:
                result = await tool_fn.ainvoke(call["args"])
            messages.append(
                ToolMessage(content=json.dumps(result, default=str), tool_call_id=call["id"])
            )
            tool_calls_made += 1
    return ai_messages


def _validate(
    strategy: Strategy, kind: DecisionKind, parsed: BaseModel, situation: Situation
) -> str | None:
    """Every proposed operation kind must be in `strategy.allowed_operations`
    (itself `⊂ OperationKind`), and every referenced id/attack/choice must
    pass `operations.validate_refs`, wrapping the proposal in a synthetic
    `Operation` since that is what `validate_refs` takes."""
    if kind is DecisionKind.READ_MOVE:
        proposed = parsed.proposed  # type: ignore[attr-defined]
        if proposed:
            for op in proposed:
                if op.kind not in set(OperationKind):
                    return "unknown_operation_kind"
                operation_kind = OperationKind(op.kind)
                if operation_kind not in strategy.allowed_operations:
                    return "disallowed_operation"
                synthetic = Operation(
                    operation_id="proposed", kind=operation_kind, payload=op.payload
                )
                reason = validate_refs(situation, synthetic)
                if reason is not None:
                    return reason
        return None

    if kind is DecisionKind.MONSTER_ACTION:
        synthetic = Operation(
            operation_id="proposed",
            kind=OperationKind.RESOLVE_ATTACK,
            payload={
                "actor_id": parsed.actor_id,  # type: ignore[attr-defined]
                "target_id": parsed.target_id,  # type: ignore[attr-defined]
                "attack": parsed.attack,  # type: ignore[attr-defined]
            },
        )
        return validate_refs(situation, synthetic)

    if kind is DecisionKind.JUDGE_REFERENCE:
        chosen_id = parsed.chosen_id  # type: ignore[attr-defined]
        if chosen_id is not None:
            synthetic = Operation(
                operation_id="proposed", kind=OperationKind.INTERACT, payload={"choice": chosen_id}
            )
            return validate_refs(situation, synthetic)
        return None

    if kind is DecisionKind.WORLD_REACTION:
        for reaction in parsed.reactions:  # type: ignore[attr-defined]
            operation_kind_name = reaction.kind
            if operation_kind_name not in set(OperationKind):
                continue
            operation_kind = OperationKind(operation_kind_name)
            if operation_kind not in strategy.allowed_operations:
                continue
            synthetic = Operation(
                operation_id="proposed", kind=operation_kind, payload=reaction.payload
            )
            reason = validate_refs(situation, synthetic)
            if reason is not None:
                return reason
        return None

    return None


async def decide(
    ctx: DecisionContext, request: DecisionRequest, state: GameFlowState
) -> DecisionResult:
    strategy = DECISION_HANDLERS[request.kind]
    prompt = load_prompt(f"game/decision/{strategy.prompt_key}")
    evidence = strategy.evidence(ctx.situation, state)
    system_message = SystemMessage(content=prompt.text)
    label = f"decision-{request.kind}"

    ai_messages: list[AIMessage] = []
    reason: str | None = None
    for _attempt in range(RETRY_BUDGET + 1):
        human_content: dict[str, Any] = {
            "evidence": evidence,
            "request": dict(request.payload),
            "evidence_ids": list(request.evidence_ids),
            "allowed_operations": sorted(op.value for op in strategy.allowed_operations),
        }
        if reason is not None:
            human_content["previous_error"] = reason
        messages: list[Any] = [
            system_message,
            HumanMessage(content=json.dumps(human_content, default=str)),
        ]

        if strategy.binds_tools:
            ai_messages.extend(await _run_tool_loop(ctx, ctx.model, messages, label=label))

        structured = ctx.model.with_structured_output(strategy.output_schema, include_raw=True)
        result = await structured.ainvoke(messages)
        parsed = result["parsed"]
        raw = result["raw"]
        ai_messages.append(raw)

        reason = _validate(strategy, request.kind, parsed, ctx.situation)
        if reason is None:
            value = strategy.build(parsed, ctx.situation)
            usage = model_call.to_usage(ai_messages)
            return DecisionResult(
                decision_id=request.decision_id, kind=request.kind, value=value, usage=usage
            )

    raise DecisionInvalid(f"{request.kind}: {reason}")
