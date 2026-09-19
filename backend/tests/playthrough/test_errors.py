"""I4: every `PlaythroughError` subclass carries the domain code the route
layer maps straight onto `ApiError` -- the one thing this hierarchy exists
to guarantee."""

from app.core.errors import ErrorCode
from app.modules.playthrough.errors import (
    CampaignNotFoundError,
    CampaignRunExistsError,
    CampaignRunNotFoundError,
    CharacterExistsError,
    InvalidRunStatusError,
    PlaythroughError,
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
