"""Narration: one unbound model call per beat over public data only
(sprint 011/06, WI2, intent §5).

Narration is deliberately not a decision. It never sees `Situation`
(private): only `Situation.public()` -- which already strips `secrets`,
`npc_intent` and every `FixtureView.checks` (`playthrough.situation`) --
plus the player's own accepted action text and the subset of recorded
events named by `BeatRequest.allowed_evidence_ids`. The model is used
unbound (no `bind_tools`): narration performs no write and decides
nothing, so it has no tool to call.

`record_beat` contract: `narrate()` only drafts. Its `BeatDraft` becomes
`state["narrative"]` via `draft_state()` and stays there -- `draft` set,
`event_id` `None` -- until the `RECORD_BEAT` operation (`agent/
operations_world.py`) persists it and reports `ok`. Only then does the
caller apply `recorded_state()`, which clears `draft` and sets `event_id`;
a beat whose `RECORD_BEAT` never lands (a crashed or retried turn) leaves
its draft sitting in the checkpoint rather than a half-written event in
the database.
"""

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.prompts.service import load_prompt
from app.modules.game.agent import model_call
from app.modules.game.agent.flow_state import GameFlowState, NarrativeCursor, StateDelta, Usage
from app.modules.playthrough.situation import Situation

PROMPT_ID = "game/narration/beat"

BeatKind = Literal["opening", "attempt", "outcome", "answer", "arrival", "refusal", "closing"]


class NarrationContext(Protocol):
    """The slice of a call context `narrate()` needs -- kept local rather
    than imported from `decisions.py` so the two modules stay uncoupled;
    the real `DecisionContext` satisfies this by shape alone."""

    situation: Situation
    model: BaseChatModel


@dataclass(frozen=True)
class BeatRequest:
    beat_id: str
    kind: BeatKind
    allowed_evidence_ids: tuple[str, ...]
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class BeatDraft:
    beat_id: str
    text: str
    usage: Usage


def _facts(ctx: NarrationContext, request: BeatRequest, state: GameFlowState) -> Mapping[str, Any]:
    """The JSON-serialisable fact set the model is shown: the public
    situation, the accepted player action text, the recorded events named
    by `allowed_evidence_ids` and the request's own public payload --
    nothing else. `Situation.public()` already strips `secrets`,
    `npc_intent` and every `FixtureView.checks`."""
    public = ctx.situation.public()
    allowed = set(request.allowed_evidence_ids)
    evidence = tuple(event for event in public.recent if event.id in allowed)
    return {
        "kind": request.kind,
        "situation": asdict(public) | {"recent": [asdict(event) for event in evidence]},
        "player_action": state["turn"].text,
        "facts": dict(request.payload),
    }


async def narrate(ctx: NarrationContext, request: BeatRequest, state: GameFlowState) -> BeatDraft:
    """Draft one beat's narration text from public data only.

    Builds a `SystemMessage` from the versioned narration prompt and a
    `HumanMessage` carrying `_facts()` as JSON, invokes `ctx.model`
    unbound (never `bind_tools`) through `model_call.ainvoke`, and returns
    the drafted text plus its usage. Performs no database write.
    """
    system_prompt = load_prompt(PROMPT_ID).text
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(_facts(ctx, request, state), default=str)),
    ]
    reply = await model_call.ainvoke(ctx.model, messages, label=f"narration:{request.kind}")
    usage = model_call.to_usage([reply])
    text = reply.content if isinstance(reply.content, str) else json.dumps(reply.content)
    return BeatDraft(beat_id=request.beat_id, text=text, usage=usage)


def draft_state(draft: BeatDraft) -> StateDelta:
    """The draft survives in `state["narrative"]` until `RECORD_BEAT`
    reports `ok` -- see the module docstring."""
    return {"narrative": NarrativeCursor(beat_id=draft.beat_id, draft=draft.text, event_id=None)}


def recorded_state(beat_id: str, event_id: str) -> StateDelta:
    """Applied once `RECORD_BEAT` has persisted the draft: clears `draft`,
    sets `event_id`."""
    return {"narrative": NarrativeCursor(beat_id=beat_id, draft=None, event_id=event_id)}
