"""Pure-unit coverage of `app/core/ids.py` (`shared-knowledge.md` D38): every
primary key in the domain is a 26-character Crockford base32 ULID string, not
a `uuid.UUID`. The wire-level round-trip (an id emitted by a route staying a
26-character string) is covered by `tests/auth/test_register.py`.
"""

import re

from app.core.ids import ID_LENGTH, generate_id

ULID_PATTERN = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")  # Crockford base32, no I/L/O/U


def test_generate_id_is_a_26_character_crockford_base32_ulid_string():
    identifier = generate_id()
    assert isinstance(identifier, str)
    assert len(identifier) == ID_LENGTH == 26
    assert ULID_PATTERN.fullmatch(identifier)


def test_generate_id_is_unique_per_call():
    assert generate_id() != generate_id()
