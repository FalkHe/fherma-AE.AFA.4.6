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


class CreationConversationNotFoundError(Exception):
    """No live creation conversation answers `conversation_id` in
    `app.state` -- an unknown id, one from another caller, or one whose
    caller has lost membership in the run since starting it, all
    indistinguishable on purpose (sprint 009-05, ← research Decision 2),
    the same way `playthrough.errors.CampaignRunNotFoundError` treats an
    unknown and a foreign run alike."""

    code = ErrorCode.NOT_FOUND

    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        super().__init__(f"creation conversation not found: {conversation_id}")
