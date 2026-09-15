"""Sprint 02 WI1: the eight LLM failure codes exist on the HTTP wire behind
one shared message (← D2 - the player sees one generic line regardless of
which failure occurred; the code is for us, not for them).

`LlmError` gains its `code: ErrorCode` attribute in sprint 02's WI2
(`core/llm/errors.py`), landing separately from this file. Until it does,
`register_error_handlers`'s `@app.exception_handler(LlmError)` cannot be
exercised end-to-end - there is no `LlmError` instance with a `.code` to
raise. These tests instead pin the wire contract this work item owns: the
`ErrorCode` members, their shared `(502, LLM_FAILURE_MESSAGE)` row, and the
message text itself.
"""

import pytest

from app.core.errors import _ERROR_INFO, LLM_FAILURE_MESSAGE, ErrorCode

LLM_CODES = [
    ErrorCode.LLM_AUTH,
    ErrorCode.LLM_BUDGET,
    ErrorCode.LLM_RATE_LIMIT,
    ErrorCode.LLM_TIMEOUT,
    ErrorCode.LLM_REFUSED,
    ErrorCode.LLM_UNAVAILABLE,
    ErrorCode.LLM_MALFORMED,
    ErrorCode.LLM_BAD_REQUEST,
]


def test_eight_llm_codes_are_members_of_error_code():
    names = {code.name for code in LLM_CODES}
    assert names == {
        "LLM_AUTH",
        "LLM_BUDGET",
        "LLM_RATE_LIMIT",
        "LLM_TIMEOUT",
        "LLM_REFUSED",
        "LLM_UNAVAILABLE",
        "LLM_MALFORMED",
        "LLM_BAD_REQUEST",
    }


@pytest.mark.parametrize("code", LLM_CODES)
def test_llm_code_value_matches_its_name(code):
    # Follows the file's existing convention (e.g. VALIDATION_ERROR = "VALIDATION_ERROR").
    assert code.value == code.name


@pytest.mark.parametrize("code", LLM_CODES)
def test_llm_code_resolves_to_502_and_the_shared_message(code):
    status_code, message = _ERROR_INFO[code]
    assert status_code == 502
    assert message == LLM_FAILURE_MESSAGE


def test_llm_failure_message_is_the_generic_player_facing_line():
    assert LLM_FAILURE_MESSAGE == "The AI service could not complete that request."


def test_all_eight_llm_codes_share_the_identical_message():
    # D2: one status, one wording for all eight - never a per-code hint.
    messages = {_ERROR_INFO[code][1] for code in LLM_CODES}
    assert messages == {LLM_FAILURE_MESSAGE}
