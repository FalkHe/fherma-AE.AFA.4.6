"""I4: every `PlaythroughError` subclass carries the domain code the route
layer maps straight onto `ApiError` -- the one thing this hierarchy exists
to guarantee."""

from app.core.errors import ErrorCode
from app.modules.playthrough.errors import (
    ActionNotAvailableError,
    AdventureActiveError,
    AdventureExhaustedError,
    CampaignNotFoundError,
    CampaignRunExistsError,
    CampaignRunNotFoundError,
    CharacterExistsError,
    ExitNotAvailableError,
    GameObjectNotFoundError,
    InvalidDcError,
    InvalidRunStatusError,
    PlaythroughError,
    RollNotFoundError,
    RollNotUsableError,
    RollRequiredError,
    RunArchivedError,
)


def test_campaign_run_not_found_carries_not_found():
    exc = CampaignRunNotFoundError("run-1")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.NOT_FOUND


def test_campaign_not_found_carries_not_found():
    exc = CampaignNotFoundError("no-such-campaign")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.NOT_FOUND


def test_campaign_run_exists_carries_already_started():
    exc = CampaignRunExistsError("greenhollow")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.ALREADY_STARTED


def test_run_archived_carries_run_archived():
    exc = RunArchivedError("run-1")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.RUN_ARCHIVED


def test_character_exists_carries_character_exists():
    exc = CharacterExistsError("run-1")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.CHARACTER_EXISTS


def test_invalid_run_status_carries_invalid_run_status():
    exc = InvalidRunStatusError("run-1")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.INVALID_RUN_STATUS


def test_adventure_active_carries_adventure_active():
    exc = AdventureActiveError("run-1")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.ADVENTURE_ACTIVE


def test_adventure_exhausted_carries_adventure_exhausted():
    exc = AdventureExhaustedError("run-1")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.ADVENTURE_EXHAUSTED


def test_game_object_not_found_carries_not_found():
    exc = GameObjectNotFoundError("object-1")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.NOT_FOUND


def test_exit_not_available_carries_exit_not_available():
    exc = ExitNotAvailableError("actor-1", "exit-1")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.EXIT_NOT_AVAILABLE


def test_roll_not_found_carries_not_found():
    exc = RollNotFoundError("roll-1")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.NOT_FOUND


def test_roll_not_usable_carries_roll_not_usable():
    exc = RollNotUsableError("roll-1")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.ROLL_NOT_USABLE


def test_invalid_dc_carries_invalid_dc():
    exc = InvalidDcError(3)
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.INVALID_DC


def test_action_not_available_carries_action_not_available():
    exc = ActionNotAvailableError("object-1", "push it")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.ACTION_NOT_AVAILABLE


def test_roll_required_carries_roll_required():
    exc = RollRequiredError("object-1", "cut it")
    assert isinstance(exc, PlaythroughError)
    assert exc.code == ErrorCode.ROLL_REQUIRED
