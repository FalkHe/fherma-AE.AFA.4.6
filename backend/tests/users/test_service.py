"""Pure-unit coverage of `app.modules.users.service.normalize_username`, the
one pure function pinned with a full signature in §6.1: `strip + lower-case`.
"""

from app.modules.users.service import normalize_username


def test_normalize_username_lowercases():
    assert normalize_username("Aragorn") == "aragorn"


def test_normalize_username_strips_surrounding_whitespace():
    assert normalize_username("  aragorn  ") == "aragorn"


def test_normalize_username_strips_and_lowercases_together():
    assert normalize_username("  ARAGORN  ") == "aragorn"
