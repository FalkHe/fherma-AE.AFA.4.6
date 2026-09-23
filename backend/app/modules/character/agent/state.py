"""`CreationContext` is the graph's `context_schema`: what the write needs
and the model must never be able to supply. It reaches a tool through
`ToolRuntime`, so it is absent from every tool's model-facing schema
(same seam as `game.agent.state.DmContext`).
"""

from dataclasses import dataclass, field
from typing import Annotated, Any, NotRequired

from langgraph.graph import MessagesState
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.schemas import SeedCharacter


@dataclass
class CreationContext:
    db: AsyncSession
    user_id: str
    run_id: str
    ready_made: SeedCharacter | None = None
    ready_made_items: list[str] = field(default_factory=list)


def _merge_draft(current: dict[str, Any] | None, update: dict[str, Any]) -> dict[str, Any]:
    """A single model step can carry two draft-writing tool calls at once
    (e.g. "suggest the scores and show me the sheet"); a plain last-value
    channel raises `InvalidUpdateError` on the second write in that step.
    Each writing tool now returns only its own delta, and this reducer
    merges them -- last write wins per key. `None` removes a stale key,
    such as equipment picks after a class change."""
    merged = dict(current or {})
    for key, value in update.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


class CreationState(MessagesState):
    """`draft` accumulates the keys of a `CharacterCreateRequest` as the
    player and the agent settle them: `name`, `race`, `character_class`,
    `abilities`, `appearance`, `backstory`. `saved` flips once
    `save_character` has written the run's character."""

    draft: NotRequired[Annotated[dict[str, Any], _merge_draft]]
    saved: NotRequired[bool]
