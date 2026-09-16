"""Sprint 07 WI1 — `app/core/checkpointer/service.py`: `checkpointer_conn_string`
(← research.md Interfaces).

`checkpointer_conn_string` is a pure function; this file is its only
coverage. Everything else in `service.py` (`checkpointer()`, `ensure_schema()`,
`setup()`) opens a real Postgres connection, which `backend/tests/conftest.py`
forbids the suite from ever doing - those three are hand-run checks
(research.md's "Live check"), not unit tests here."""

from app.core.checkpointer.service import checkpointer_conn_string


def test_strips_the_driver_tag_and_pins_search_path_to_the_checkpointer_schema():
    """The example pinned exactly by the sprint's interface contract."""
    assert (
        checkpointer_conn_string("postgresql+psycopg://app:app@postgres:5432/application")
        == "postgresql://app:app@postgres:5432/application?options=-csearch_path%3Dcheckpoints"
    )


def test_leaves_a_url_with_no_driver_tag_unchanged_besides_the_added_query():
    assert (
        checkpointer_conn_string("postgresql://app:app@postgres:5432/application")
        == "postgresql://app:app@postgres:5432/application?options=-csearch_path%3Dcheckpoints"
    )


def test_preserves_existing_query_parameters_ahead_of_options():
    assert (
        checkpointer_conn_string(
            "postgresql+psycopg://app:app@postgres:5432/application?sslmode=require"
        )
        == "postgresql://app:app@postgres:5432/application"
        "?sslmode=require&options=-csearch_path%3Dcheckpoints"
    )


def test_passes_a_password_with_special_characters_through_untouched():
    """The netloc (user:pass@host:port) is never re-parsed or re-encoded -
    only the scheme is trimmed and the query rebuilt - so an already-escaped
    password survives byte-for-byte."""
    assert (
        checkpointer_conn_string("postgresql+psycopg://app:p%40ss%3Aword@postgres:5432/application")
        == "postgresql://app:p%40ss%3Aword@postgres:5432/application"
        "?options=-csearch_path%3Dcheckpoints"
    )


def test_escapes_the_inner_equals_sign_in_the_options_value():
    """`%3D`, not a literal `=` - a second, unescaped `=` inside the query
    string's `options` value would parse as a second key, which is what
    `psycopg.ProgrammingError: missing "=" after ...` (research.md) comes
    from getting this wrong."""
    conn_string = checkpointer_conn_string("postgresql+psycopg://app:app@postgres:5432/application")
    assert "-csearch_path%3Dcheckpoints" in conn_string
    assert "-csearch_path=checkpoints" not in conn_string
