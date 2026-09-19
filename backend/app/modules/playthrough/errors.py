"""Every failure `playthrough/service.py` can raise.

Each subclass carries `code: ErrorCode`, the shared domain code the route
layer maps straight onto the wire envelope:
`except PlaythroughError as exc: raise ApiError(exc.code) from exc` -- this
module never builds that envelope itself (precedent: `content/errors.py`,
`srd/errors.py`, `core/llm/errors.py`).
"""

from app.core.errors import ErrorCode


class PlaythroughError(Exception):
    """Base for every playthrough failure.

    `code` is a bare annotation, deliberately without a default -- a
    subclass that forgets it is a bug to surface, not to paper over here.
    """

    code: ErrorCode


class CampaignRunNotFoundError(PlaythroughError):
    """No campaign run answers `run_id` for this caller.

    Raised alike whether the id is unknown outright or belongs to someone
    else -- the two are indistinguishable on purpose (← D12).
    `_require_member` is the only place either can originate.
    """

    code = ErrorCode.NOT_FOUND

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"campaign run not found: {run_id}")


class CampaignNotFoundError(PlaythroughError):
    """No shipped content answers `campaign_id`.

    Always raised `from` the `ContentNotFoundError` it wraps, so the
    content module's own error hierarchy never crosses into this one.
    """

    code = ErrorCode.NOT_FOUND

    def __init__(self, campaign_id: str) -> None:
        self.campaign_id = campaign_id
        super().__init__(f"campaign not found: {campaign_id}")


class CampaignRunExistsError(PlaythroughError):
    """A repeat start collided with the `(campaign_run_id, instance_key)`
    unique constraint.

    Translated from the `IntegrityError` it caused; there is no pre-check.
    """

    code = ErrorCode.ALREADY_STARTED

    def __init__(self, campaign_id: str) -> None:
        self.campaign_id = campaign_id
        super().__init__(f"campaign run already started: {campaign_id}")


class RunArchivedError(PlaythroughError):
    """The run is `archived`, which refuses every write.

    Raised by `_require_writable` -- rename, character creation, and
    sprint 06's `enter_adventure` all call it first. There is no unarchive:
    an archived run stays read-only forever.
    """

    code = ErrorCode.RUN_ARCHIVED

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"campaign run is archived: {run_id}")


class CharacterExistsError(PlaythroughError):
    """This run's member already has a character.

    A Stage-01 game rule enforced in the service, not the schema (← 003-
    D13): nothing in the `objects` table stops a second `member_id` match,
    the pre-check in `create_character` does.
    """

    code = ErrorCode.CHARACTER_EXISTS

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"campaign run already has a character: {run_id}")


class InvalidRunStatusError(PlaythroughError):
    """The run's current status does not allow the requested transition."""

    code = ErrorCode.INVALID_RUN_STATUS

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"campaign run status does not allow this transition: {run_id}")
