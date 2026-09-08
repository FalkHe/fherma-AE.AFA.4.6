"""Pure-unit coverage of `app/core/security.py` (§6.1, §6.5).

None of these five functions has a request/response contract of its own, so
they are not tied to a numbered §8 criterion directly - they back criteria 16
and 17 (Argon2 hash shape, token hash shape), which this suite can only prove
at the unit level; see the QA report for why the DB-observation half of 16/17
is out of reach of an engine-free suite.

Note on `verify_password`'s argument order: it is named and described in
`backend-stack.md` ("Argon2 ... `PasswordHasher()` with library defaults") but
its parameter order is not spelled out as a full signature the way the
service functions are. This test assumes it mirrors the wrapped library's own
`PasswordHasher.verify(hash, password)` order (hash first). If a correct
implementation chose the opposite order, only this test's call order needs to
flip - see the QA report.
"""

import re

from app.core.security import (
    generate_token,
    hash_password,
    hash_token,
    tokens_equal,
    verify_password,
)


def test_hash_password_produces_an_argon2_hash_different_from_the_input():
    hashed = hash_password("hunter-of-orcs")
    assert hashed.startswith("$argon2")
    assert hashed != "hunter-of-orcs"


def test_hash_password_is_salted_and_therefore_not_deterministic():
    assert hash_password("hunter-of-orcs") != hash_password("hunter-of-orcs")


def test_verify_password_accepts_the_correct_password_and_rejects_a_wrong_one():
    hashed = hash_password("hunter-of-orcs")
    assert verify_password(hashed, "hunter-of-orcs") is True
    assert verify_password(hashed, "wrong-password") is False


def test_generate_token_is_a_43_character_url_safe_string_and_is_unique_per_call():
    token = generate_token()
    assert isinstance(token, str)
    assert len(token) == 43  # secrets.token_urlsafe(32) -> 43 url-safe characters
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
    assert generate_token() != generate_token()


def test_hash_token_is_a_lowercase_hex_sha256_digest():
    digest = hash_token("some-session-token-value")
    assert re.fullmatch(r"[0-9a-f]{64}", digest)


def test_hash_token_is_deterministic_for_the_same_input():
    assert hash_token("some-session-token-value") == hash_token("some-session-token-value")


def test_tokens_equal_matches_identical_values_and_rejects_different_ones():
    assert tokens_equal("abc123", "abc123") is True
    assert tokens_equal("abc123", "abc124") is False
