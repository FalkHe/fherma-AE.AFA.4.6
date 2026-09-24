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


class CharacterNotFoundError(PlaythroughError):
    """This run's member has no character yet.

    `get_member_character` is the only place this can originate: it
    raises `_require_member`'s `CampaignRunNotFoundError` first, so this
    is reachable only once the caller is already a known member of a
    known run.
    """

    code = ErrorCode.NOT_FOUND

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"campaign run has no character yet: {run_id}")


class InvalidRunStatusError(PlaythroughError):
    """The run's current status does not allow the requested transition."""

    code = ErrorCode.INVALID_RUN_STATUS

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"campaign run status does not allow this transition: {run_id}")


class AdventureActiveError(PlaythroughError):
    """This run already has another adventure `active`.

    Translated from the `IntegrityError` `uq_adventure_runs_active`
    raises when `enter_adventure` tries to insert a second `active` row
    for the same run -- there is no pre-check. Only that constraint is
    caught; any other integrity failure propagates unchanged.
    """

    code = ErrorCode.ADVENTURE_ACTIVE

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"campaign run already has an active adventure: {run_id}")


class AdventureExhaustedError(PlaythroughError):
    """Every adventure the pinned campaign declares already has an
    `adventure_runs` row in this run -- there is nothing left to enter.

    Raised alike whether every adventure has been played through or the
    caller is re-entering one that already completed: both leave no
    adventure id without a row (← AC4).
    """

    code = ErrorCode.ADVENTURE_EXHAUSTED

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"campaign run has no adventure left to enter: {run_id}")


class GameObjectNotFoundError(PlaythroughError):
    """No object answers `actor_id`, on its own, with no membership context
    yet -- `use_exit` (sprint 06b) loads the actor before it knows which
    run to check membership against."""

    code = ErrorCode.NOT_FOUND

    def __init__(self, object_id: str) -> None:
        self.object_id = object_id
        super().__init__(f"object not found: {object_id}")


class RollRequestNotFoundError(PlaythroughError):
    """No `roll_requested` event answers `request_id` -- either no event
    at all, or one of a different type. `resolve_roll_request` is the only
    place this can originate; there is no membership context yet, exactly
    the way `GameObjectNotFoundError` has none for `use_exit`."""

    code = ErrorCode.NOT_FOUND

    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        super().__init__(f"roll request not found: {request_id}")


class RollNotFoundError(PlaythroughError):
    """No `roll` event answers `roll_id` -- either no event at all, or one
    of a different type. `_get_roll_event` is the only place this can
    originate; there is no membership context yet, exactly the way
    `GameObjectNotFoundError` has none for `use_exit` and
    `RollRequestNotFoundError` has none for `resolve_roll_request`. A roll
    that belongs to another game answers identically (← D12) -- `_consume_roll`
    is the other place this can originate, once a run is already known."""

    code = ErrorCode.NOT_FOUND

    def __init__(self, roll_id: str) -> None:
        self.roll_id = roll_id
        super().__init__(f"roll not found: {roll_id}")


class RollNotUsableError(PlaythroughError):
    """`roll_id` cannot be spent by this call: it was already spent by an
    earlier *successful* `tool_call` naming it, it was made in another
    turn (both untagged counting as equal), or it is of a kind the
    consuming mechanic does not accept -- a `custom` roll fails every
    check, deliberately. Always raised after the refusal is already
    recorded as a `tool_call` event and committed (← D11)."""

    code = ErrorCode.ROLL_NOT_USABLE

    def __init__(self, roll_id: str) -> None:
        self.roll_id = roll_id
        super().__init__(f"roll not usable: {roll_id}")


class InvalidDcError(PlaythroughError):
    """`dc` fell outside the SRD's own 5-30 difficulty range (← D6, D11).
    Always raised after the refusal is already recorded as a `tool_call`
    event and committed."""

    code = ErrorCode.INVALID_DC

    def __init__(self, dc: int) -> None:
        self.dc = dc
        super().__init__(f"invalid dc: {dc}")


class ObjectNotReachableError(PlaythroughError):
    """`item_id` cannot be moved by this attempt right now.

    Covers every reachability refusal `take`, `drop` and `give` share: the
    item lies in another scene, it is carried by a creature other than the
    actor asking, the actor itself has no current scene to act from, or --
    for `give` specifically -- the item is not currently carried by the
    giver, or the receiver is not a creature standing in the giver's own
    scene. `take` alone widens this beyond a bare scene match: an item
    whose owner is a non-creature object (a fixture such as a container)
    standing in the actor's scene is reachable too (AC5). Always raised
    after the refusal is already recorded as a `tool_call` event and
    committed."""

    code = ErrorCode.OBJECT_NOT_REACHABLE

    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(f"object not reachable: {item_id}")


class HitNotUsableError(PlaythroughError):
    """`hit_id` cannot be spent by `damage`: either no `attack` `tool_call`
    of this run answers it at all, or the one that does fails one of its
    usability conditions -- it did not succeed, it landed as a `miss`, it
    belongs to another turn, its own recorded target does not match the
    `target_id` argument, or it has already been damaged by an earlier
    *successful* `damage` this turn. Deliberately one error for every one
    of those, the way a `custom` roll fails `_consume_roll` for a single
    reason regardless of which check it is -- the caller is told a hit was
    not usable, never handed a menu of which specific condition failed.
    Always raised after the refusal is already recorded as a `tool_call`
    event and committed (← D11)."""

    code = ErrorCode.HIT_NOT_USABLE

    def __init__(self, hit_id: str) -> None:
        self.hit_id = hit_id
        super().__init__(f"hit not usable: {hit_id}")


class InvalidEventPayloadError(PlaythroughError):
    """`append_event` was asked to write a `type` or `visibility` it does
    not know, or a `payload` that fails the model `EVENT_PAYLOADS[type]`
    declares.

    Nothing is written when this fires -- no `add`, no `flush` -- so a
    caller sees a raised exception, never a partial row.
    """

    code = ErrorCode.VALIDATION_ERROR

    def __init__(self, message: str) -> None:
        super().__init__(message)
