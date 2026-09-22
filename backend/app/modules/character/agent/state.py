"""`CreationContext` is the graph's `context_schema`: what the write needs
and the model must never be able to supply. It reaches a tool through
`ToolRuntime`, so it is absent from every tool's model-facing schema
(same seam as `game.agent.state.DmContext`).
"""

from dataclasses import dataclass
from typing import Any, NotRequired

from langgraph.graph import MessagesState
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.schemas import SeedCharacter


@dataclass
class CreationContext:
    db: AsyncSession
    user_id: str
    run_id: str
    ready_made: SeedCharacter | None = None


class CreationState(MessagesState):
    """`draft` accumulates the keys of a `CharacterCreateRequest` as the
    player and the agent settle them: `name`, `race`, `character_class`,
    `abilities`, `appearance`, `backstory`. `saved` flips once
    `save_character` has written the run's character."""

    draft: NotRequired[dict[str, Any]]
    saved: NotRequired[bool]
