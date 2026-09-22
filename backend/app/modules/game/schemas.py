"""Wire shapes for the turn route (I1, sprint 03 WI2). Nothing here rolls
a die or writes an event -- `game.service.run_turn` alone decides `kind`
and `awaiting` from the run's own state; the request carries no kind and
no dice number on purpose."""

from typing import Literal

from pydantic import ConfigDict, Field

from app.core.schemas import CamelModel

TurnKind = Literal["action", "answer", "roll", "retry", "opening"]


class TurnRequest(CamelModel):
    """The turn route's whole request body (I1) -- `text` and nothing
    else. `extra="forbid"` enforces that: a caller naming a turn kind or
    a dice number is refused with `VALIDATION_ERROR`, never silently
    ignored -- that refusal is the point of the design, not an
    afterthought."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=2000)


class TurnRead(CamelModel):
    """The turn route's whole response body (I1) -- `turnId`, `kind` and
    `awaiting`. `awaiting` mirrors `playthrough.schemas.EventsRead`'s own
    field: `"none"`, `"roll:<id>"` or `"answer:<id>"`, read fresh from
    `playthrough.service.get_awaiting` after the turn runs."""

    turn_id: str
    kind: TurnKind
    awaiting: str
