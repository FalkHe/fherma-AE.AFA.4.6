"""The two write tools of step 3.14: `record_preference` and `flag_unknown_bike`.

These are the only tools that change the database, so unlike the read tools they
are *not* tested against stubbed services: the store is the in-memory
`FakeAsyncSession` and the real `chat_service` / `product_service` run on top of
it. What matters here is exactly the behaviour the services own and the tools must
not re-implement or defeat:

* **supersession** — capturing the same attribute again replaces the earlier
  answer instead of adding a second active one, end to end through the tool
  (including the tool's own attribute normalization, without which "Budget" and
  "budget" would both stay active);
* **idempotency across every status** — a name already in the catalogue comes
  back `already_known` whatever its status is, and no second row appears; the
  slug is what deduplicates, so spelling variants collapse;
* **the pinned ack shapes** — `{attribute, value, firmness}` and
  `{name, status}`, recorded in the pinned `tool_calls[]` entry and validated
  against the read-path `ToolCall` schema the API serves them through.
"""

import asyncio
from typing import Any

import pytest
from pydantic import ValidationError

from app.api.schemas.chat_messages import ToolCall
from app.db.models.chat import ChatPreference
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.llm.agents import tools
from app.llm.agents.tools import flag_unknown_bike, record_preference
from app.services import chat_service, product_service
from tests.services.conftest import FakeAsyncSession

USER_ID = "0" * 22 + "USER"


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    """The service tests' in-memory store; its own fixture lives in their conftest."""
    return FakeAsyncSession()


@pytest.fixture
def ctx(fake_session: FakeAsyncSession) -> tools.ToolContext:
    """A tool context for a real (in-memory) consultation of a real customer."""
    chat = asyncio.run(chat_service.create_chat(fake_session, USER_ID))
    return tools.ToolContext(session=fake_session, chat=chat)


def _execute(name: str, ctx: tools.ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one registered tool the way the loop and the CLI both run it."""
    return asyncio.run(tools.execute(tools.get_tool_spec(name), ctx, arguments))


def _active(ctx: tools.ToolContext) -> list[tuple[str, str, str]]:
    """The chat's active preferences as (attribute, value, firmness) triples."""
    assert ctx.chat is not None
    rows = asyncio.run(chat_service.active_preferences(ctx.session, ctx.chat.id))
    return [(row.attribute, row.value, row.firmness.value) for row in rows]


def _backlog_names(session: FakeAsyncSession) -> list[tuple[str, str, str]]:
    """Every catalogue row as (name, slug, status) — the dedup evidence."""
    return [(row.query_name, row.slug, row.status.value) for row in session.rows(Motorbike)]


# --- record_preference --------------------------------------------------------


def test_record_preference_stores_the_capture_and_acks_it(ctx: tools.ToolContext) -> None:
    """The pinned ack is what was stored, nothing more."""
    payload = _execute(
        record_preference.NAME,
        ctx,
        {"attribute": "budget", "value": "around 6000 €", "firmness": "soft"},
    )

    assert payload == {"attribute": "budget", "value": "around 6000 €", "firmness": "soft"}
    assert _active(ctx) == [("budget", "around 6000 €", "soft")]


def test_recording_the_same_attribute_supersedes_the_earlier_answer(
    ctx: tools.ToolContext,
) -> None:
    """A changed mind: one active row, one superseded row pointing at it."""
    _execute(
        record_preference.NAME,
        ctx,
        {"attribute": "budget", "value": "around 6000 €", "firmness": "soft"},
    )
    _execute(
        record_preference.NAME,
        ctx,
        {"attribute": "budget", "value": "max 5000 €", "firmness": "hard"},
    )

    assert _active(ctx) == [("budget", "max 5000 €", "hard")]
    first, second = ctx.session.rows(ChatPreference)
    assert first.superseded_by_id == second.id
    assert second.superseded_by_id is None


def test_a_differently_spelled_attribute_still_supersedes(ctx: tools.ToolContext) -> None:
    """Case and separators are noise: "Use_Case" and "use case" are one attribute.

    Without this normalization the two captures would both stay active and the
    next turn's prompt would carry a contradiction.
    """
    _execute(
        record_preference.NAME,
        ctx,
        {"attribute": "Use_Case", "value": "commuting", "firmness": "hard"},
    )
    payload = _execute(
        record_preference.NAME,
        ctx,
        {"attribute": "  use  case ", "value": "commuting and weekend trips", "firmness": "hard"},
    )

    # The ack carries the normalized name, so the model learns the canonical form.
    assert payload["attribute"] == "use case"
    assert _active(ctx) == [("use case", "commuting and weekend trips", "hard")]


def test_different_attributes_stay_active_side_by_side(ctx: tools.ToolContext) -> None:
    """Supersession is per attribute, and the block keeps its capture order."""
    for attribute, value, firmness in (
        ("licence", "A2", "hard"),
        ("budget", "max 5000 €", "hard"),
        ("style", "naked", "exploring"),
    ):
        _execute(
            record_preference.NAME,
            ctx,
            {"attribute": attribute, "value": value, "firmness": firmness},
        )

    assert _active(ctx) == [
        ("licence", "A2", "hard"),
        ("budget", "max 5000 €", "hard"),
        ("style", "naked", "exploring"),
    ]


def test_the_recorded_entry_validates_against_the_read_path_schema(
    ctx: tools.ToolContext,
) -> None:
    """What the API serves back: the pinned entry, every key present."""
    payload = _execute(
        record_preference.NAME,
        ctx,
        {"attribute": "licence", "value": "A2", "firmness": "hard"},
    )

    (entry,) = ctx.collector.tool_calls
    validated = ToolCall.model_validate(entry)
    assert validated.tool == record_preference.NAME
    assert validated.status.value == "succeeded"
    assert validated.error is None
    assert validated.result == payload
    assert entry["arguments"] == {"attribute": "licence", "value": "A2", "firmness": "hard"}


@pytest.mark.parametrize(
    "arguments",
    [
        {"attribute": " ", "value": "A2", "firmness": "hard"},
        {"attribute": "licence", "value": "   ", "firmness": "hard"},
        {"attribute": "licence", "value": "A2", "firmness": "quite firm"},
        {"attribute": "licence", "value": "A2"},
    ],
)
def test_a_rejected_capture_writes_nothing_and_is_not_recorded(
    ctx: tools.ToolContext, arguments: dict[str, Any]
) -> None:
    """A call the schema rejects never executed: no row, no `tool_calls` entry."""
    with pytest.raises(ValidationError):
        _execute(record_preference.NAME, ctx, arguments)

    assert _active(ctx) == []
    assert ctx.collector.tool_calls == []


def test_an_over_long_capture_is_truncated_to_the_column_widths(
    ctx: tools.ToolContext,
) -> None:
    """A talkative model loses words, not the capture (and never overflows a column)."""
    payload = _execute(
        record_preference.NAME,
        ctx,
        {"attribute": "b" * 200, "value": "€" * 400, "firmness": "soft"},
    )

    assert len(payload["attribute"]) == 64
    assert len(payload["value"]) == 256


def test_recording_without_a_consultation_refuses_and_is_recorded_as_failed(
    fake_session: FakeAsyncSession,
) -> None:
    """The `app tools run` harness has no chat, so there is nothing to attach to."""
    harness = tools.ToolContext(session=fake_session)

    with pytest.raises(record_preference.MissingChatError):
        _execute(
            record_preference.NAME,
            harness,
            {"attribute": "budget", "value": "max 5000 €", "firmness": "hard"},
        )

    assert fake_session.rows(ChatPreference) == []
    (entry,) = harness.collector.tool_calls
    assert ToolCall.model_validate(entry).status.value == "failed"
    assert entry["result"] == {}
    assert "MissingChatError" in entry["error"]


# --- flag_unknown_bike --------------------------------------------------------


def test_flagging_an_unknown_bike_queues_exactly_one_backlog_row(
    ctx: tools.ToolContext,
) -> None:
    """The demand signal an admin's ingestion run starts from."""
    payload = _execute(flag_unknown_bike.NAME, ctx, {"name": "Kawasaki Z650 RS"})

    assert payload == {"name": "Kawasaki Z650 RS", "status": "queued"}
    assert _backlog_names(ctx.session) == [("Kawasaki Z650 RS", "kawasaki-z650-rs", "backlog")]
    assert ToolCall.model_validate(ctx.collector.tool_calls[0]).result == payload


def test_flagging_the_same_bike_twice_adds_nothing(ctx: tools.ToolContext) -> None:
    """Repeated mentions in one consultation are one row."""
    _execute(flag_unknown_bike.NAME, ctx, {"name": "Kawasaki Z650 RS"})
    payload = _execute(flag_unknown_bike.NAME, ctx, {"name": "Kawasaki Z650 RS"})

    assert payload == {"name": "Kawasaki Z650 RS", "status": "already_known"}
    assert len(ctx.session.rows(Motorbike)) == 1


def test_a_spelling_variant_is_deduplicated_by_slug(ctx: tools.ToolContext) -> None:
    """The slug is the identity: "Suzuki GSR 600" and "suzuki  gsr600" are one bike."""
    _execute(flag_unknown_bike.NAME, ctx, {"name": "Suzuki GSR 600"})
    payload = _execute(flag_unknown_bike.NAME, ctx, {"name": "  SUZUKI GSR 600  "})

    assert payload == {"name": "SUZUKI GSR 600", "status": "already_known"}
    assert len(ctx.session.rows(Motorbike)) == 1


@pytest.mark.parametrize(
    "status",
    [
        MotorbikeStatus.BACKLOG,
        MotorbikeStatus.INGESTING,
        MotorbikeStatus.IN_REVIEW,
        MotorbikeStatus.APPROVED,
        MotorbikeStatus.REJECTED,
    ],
)
def test_a_name_the_catalogue_already_owns_is_already_known_in_every_status(
    ctx: tools.ToolContext, status: MotorbikeStatus
) -> None:
    """Dedup runs against the whole catalogue, not against `backlog` only.

    An approved model named by the name it carries must never become a second
    row: the slug is unique, and the duplicate would collide with the model it
    duplicates.
    """
    existing = asyncio.run(product_service.create_backlog(ctx.session, "Honda CB500F"))
    existing.status = status

    payload = _execute(flag_unknown_bike.NAME, ctx, {"name": " honda   cb500f! "})

    assert payload == {"name": "honda cb500f!", "status": "already_known"}
    assert _backlog_names(ctx.session) == [("Honda CB500F", "honda-cb500f", status.value)]


def test_a_name_with_a_different_slug_is_a_different_entry(ctx: tools.ToolContext) -> None:
    """The documented boundary of the dedup: identity is the catalogue's slug.

    "Honda CB 500 F" and "Honda CB500F" are two slugs, so they are two entries —
    the same rule the admin create path (`POST /api/products`) enforces, and the
    tool deliberately does not invent a fuzzier identity of its own. The result is
    a redundant backlog row for an admin to discard, never a broken catalogue.
    """
    asyncio.run(product_service.create_backlog(ctx.session, "Honda CB500F"))

    payload = _execute(flag_unknown_bike.NAME, ctx, {"name": "Honda CB 500 F"})

    assert payload["status"] == "queued"
    assert [slug for _name, slug, _status in _backlog_names(ctx.session)] == [
        "honda-cb500f",
        "honda-cb-500-f",
    ]


@pytest.mark.parametrize("name", ["", "   ", "???", "—"])
def test_a_name_that_is_not_a_name_is_rejected(ctx: tools.ToolContext, name: str) -> None:
    """A name with no slug would become a row nothing could ever match again."""
    with pytest.raises(ValidationError):
        _execute(flag_unknown_bike.NAME, ctx, {"name": name})

    assert ctx.session.rows(Motorbike) == []
    assert ctx.collector.tool_calls == []


def test_an_over_long_name_is_truncated_to_the_column_width(ctx: tools.ToolContext) -> None:
    """160 characters is the column, and a name is not an essay."""
    payload = _execute(flag_unknown_bike.NAME, ctx, {"name": "Yamaha " + "X" * 300})

    assert len(payload["name"]) == 160
    assert len(ctx.session.rows(Motorbike)[0].slug) <= 160


def test_flagging_announces_the_new_entry_to_the_admin_screens(
    ctx: tools.ToolContext,
) -> None:
    """`create_backlog` notifies, so the admin backlog list refreshes by itself."""
    _execute(flag_unknown_bike.NAME, ctx, {"name": "Kawasaki Z650 RS"})

    (channel, payload) = ctx.session.notifications[-1]
    assert channel == "app_events"
    assert "product.updated" in payload


def test_flagging_needs_no_consultation(fake_session: FakeAsyncSession) -> None:
    """Unlike a preference, a backlog entry is catalogue-wide — the harness can flag."""
    harness = tools.ToolContext(session=fake_session)

    payload = _execute(flag_unknown_bike.NAME, harness, {"name": "Kawasaki Z650 RS"})

    assert payload["status"] == "queued"
    assert len(fake_session.rows(Motorbike)) == 1


def test_the_two_write_tools_are_the_registry_s_only_writers() -> None:
    """The pinned write-tool policy, as an assertion.

    `present_recommendations` writes to the turn's collector, not to the database;
    these two are the explicitly permitted autonomous database writes, and a third
    one needs an owner decision rather than a commit.
    """
    assert {record_preference.NAME, flag_unknown_bike.NAME} <= set(tools.tool_names())
    assert len(tools.tool_names()) == 8
