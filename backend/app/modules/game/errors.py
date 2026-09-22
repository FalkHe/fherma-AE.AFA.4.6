"""Every failure `game/service.py` raises itself, as opposed to a
`PlaythroughError` raised somewhere in `playthrough.service` that simply
propagates unchanged through `run_turn`.

`GameError` carries `code: ErrorCode` and `details`, the same shape
`PlaythroughError` and `ApiError` carry -- the route layer maps either
straight onto the wire envelope; this module never builds that envelope
itself (precedent: `playthrough/errors.py`).
"""

from typing import Any

from app.core.errors import ErrorCode


class GameError(Exception):
    """Base for every failure `game.service` raises directly.

    `code` is a bare annotation, deliberately without a default -- a
    subclass that forgets it is a bug to surface, not to paper over here.
    `details` defaults to `None`; a subclass sets it when the caller needs
    more than the message to act on the refusal.
    """

    code: ErrorCode
    details: dict[str, Any] | None = None


class ActionNotAvailableError(GameError):
    """`run_turn` was asked to answer a pending `question` interrupt with
    `text` that names none of the question's own `options` -- a question
    with no `options` accepts any text instead, so this can only fire when
    `options` is non-empty (sprint 010/03, I2 step 1).

    `details` names what the run is still awaiting (`get_awaiting`'s own
    `"answer:<id>"` shape) and the options that would have been accepted,
    so a caller can re-offer the same choice without guessing.
    """

    code = ErrorCode.ACTION_NOT_AVAILABLE

    def __init__(self, *, awaiting: str, options: list[str]) -> None:
        self.awaiting = awaiting
        self.options = options
        self.details = {"awaiting": awaiting, "options": options}
        super().__init__(f"answer not among the offered options: {awaiting}")
