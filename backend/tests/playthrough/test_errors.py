"""I4: every `PlaythroughError` subclass carries the domain code the route
layer maps straight onto `ApiError` -- the one thing this hierarchy exists
to guarantee."""

from app.core.errors import ErrorCode
from app.modules.playthrough.errors import (
    CampaignNotFoundError,
    CampaignRunExistsError,
    CampaignRunNotFoundError,
    PlaythroughError,
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
