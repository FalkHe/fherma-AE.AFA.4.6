"""Errors `builder.py` raises -- never a `ValueError`, so a route can turn
one into the project's one error envelope without guessing a code."""

from app.core.errors import ErrorCode


class CharacterBuildError(Exception):
    """`build_sheet` could not turn a `CharacterCreateRequest` into a
    `CharacterSheet` -- an illegal point-buy spread or an equipment pick
    index outside its choice's options. `.messages` names every problem
    found, not just the first."""

    code = ErrorCode.VALIDATION_ERROR

    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        super().__init__("; ".join(messages))
