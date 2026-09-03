"""QA independent verification of step 3.14 (preference capture & unknown-bike flag).

Deliberately does not import or extend `test_write_tools.py`: the dev's file is
the implementation's own proof, this one is written from the acceptance
criteria and the shared-knowledge contract alone, exercising the same tools
through the same public seam (`tools.execute` / `tools.get_tool_spec`) but with
independently constructed scenarios — including the registry write-tool
classification (by static inspection of every tool module, not by trusting the
dev's own count) and the prompt-text checks the dev's suite left implicit.
"""

import asyncio
import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.schemas.chat_messages import ToolCall
from app.db.models.chat import ChatPreference, PreferenceFirmness
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.llm.agents import advisor, tools
from app.llm.agents.tools import flag_unknown_bike, record_preference
from app.services import chat_service, product_service
from tests.services.conftest import FakeAsyncSession

USER_ID = "0" * 22 + "USER2"

TOOLS_PACKAGE_DIR = Path(tools.__file__).parent


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


@pytest.fixture
def chat_ctx(fake_session: FakeAsyncSession) -> tools.ToolContext:
    chat = asyncio.run(chat_service.create_chat(fake_session, USER_ID))
    return tools.ToolContext(session=fake_session, chat=chat)


def _execute(name: str, ctx: tools.ToolContext, arguments: dict) -> dict:
    return asyncio.run(tools.execute(tools.get_tool_spec(name), ctx, arguments))


# --- 1. record_preference end-to-end -------------------------------------------


def test_record_preference_ack_shape_is_exactly_the_pinned_three_keys(
    chat_ctx: tools.ToolContext,
) -> None:
    """The ack is `{attribute, value, firmness}` — nothing more, nothing less."""
    payload = _execute(
        record_preference.NAME,
        chat_ctx,
        {"attribute": "use case", "value": "daily 20 km commute", "firmness": "hard"},
    )

    assert set(payload) == {"attribute", "value", "firmness"}
    assert payload == {
        "attribute": "use case",
        "value": "daily 20 km commute",
        "firmness": "hard",
    }


def test_record_preference_persists_via_chat_service_row(chat_ctx: tools.ToolContext) -> None:
    """The tool created a real `chat_preferences` row through the service, not a shortcut."""
    assert chat_ctx.chat is not None
    _execute(
        record_preference.NAME,
        chat_ctx,
        {"attribute": "licence", "value": "A2", "firmness": "hard"},
    )

    (row,) = chat_ctx.session.rows(ChatPreference)
    assert row.chat_id == chat_ctx.chat.id
    assert (row.attribute, row.value, row.firmness) == ("licence", "A2", PreferenceFirmness.HARD)
    assert row.superseded_by_id is None


def test_record_preference_supersession_leaves_exactly_one_active_row(
    chat_ctx: tools.ToolContext,
) -> None:
    """Same attribute, second call: old row superseded, exactly one active survives."""
    _execute(
        record_preference.NAME,
        chat_ctx,
        {"attribute": "budget", "value": "around 6000 €", "firmness": "soft"},
    )
    _execute(
        record_preference.NAME,
        chat_ctx,
        {"attribute": "budget", "value": "max 5000 €", "firmness": "hard"},
    )

    assert chat_ctx.chat is not None
    active = asyncio.run(chat_service.active_preferences(chat_ctx.session, chat_ctx.chat.id))
    assert [row.value for row in active] == ["max 5000 €"]

    old_row, new_row = chat_ctx.session.rows(ChatPreference)
    assert old_row.superseded_by_id == new_row.id
    assert new_row.superseded_by_id is None


def test_record_preference_ack_validates_against_the_read_path_tool_call_schema(
    chat_ctx: tools.ToolContext,
) -> None:
    """What lands in `tool_calls[]` survives the frozen `ToolCall.model_validate`."""
    _execute(
        record_preference.NAME,
        chat_ctx,
        {"attribute": "style", "value": "naked", "firmness": "exploring"},
    )

    (entry,) = chat_ctx.collector.tool_calls
    validated = ToolCall.model_validate(entry)
    assert validated.tool == "record_preference"
    assert validated.status.value == "succeeded"
    assert validated.result == {"attribute": "style", "value": "naked", "firmness": "exploring"}


@pytest.mark.parametrize("bad_firmness", ["urgent", "medium", "", "HARD", None, 1])
def test_record_preference_firmness_is_restricted_to_the_three_values_at_the_args_boundary(
    chat_ctx: tools.ToolContext, bad_firmness: object
) -> None:
    """Only `hard`/`soft`/`exploring` validate — anything else never reaches the service."""
    with pytest.raises(ValidationError):
        _execute(
            record_preference.NAME,
            chat_ctx,
            {"attribute": "budget", "value": "6000 €", "firmness": bad_firmness},
        )

    assert chat_ctx.session.rows(ChatPreference) == []


# --- 2. flag_unknown_bike idempotency matrix ------------------------------------


def test_flag_unknown_bike_uncatalogued_name_queues_exactly_one_row(
    chat_ctx: tools.ToolContext,
) -> None:
    payload = _execute(flag_unknown_bike.NAME, chat_ctx, {"name": "Triumph Speed 400"})

    assert payload == {"name": "Triumph Speed 400", "status": "queued"}
    rows = chat_ctx.session.rows(Motorbike)
    assert len(rows) == 1
    assert rows[0].slug == "triumph-speed-400"
    assert rows[0].status == MotorbikeStatus.BACKLOG


def test_flag_unknown_bike_existing_approved_name_is_already_known_and_adds_no_row(
    chat_ctx: tools.ToolContext,
) -> None:
    """An approved catalogue model mentioned by name must not become a duplicate row."""
    existing = asyncio.run(product_service.create_backlog(chat_ctx.session, "Honda CB500F"))
    existing.status = MotorbikeStatus.APPROVED

    payload = _execute(flag_unknown_bike.NAME, chat_ctx, {"name": "Honda CB500F"})

    assert payload == {"name": "Honda CB500F", "status": "already_known"}
    assert len(chat_ctx.session.rows(Motorbike)) == 1


def test_flag_unknown_bike_existing_backlog_name_is_already_known(
    chat_ctx: tools.ToolContext,
) -> None:
    asyncio.run(product_service.create_backlog(chat_ctx.session, "Kawasaki Z650 RS"))

    payload = _execute(flag_unknown_bike.NAME, chat_ctx, {"name": "Kawasaki Z650 RS"})

    assert payload == {"name": "Kawasaki Z650 RS", "status": "already_known"}
    assert len(chat_ctx.session.rows(Motorbike)) == 1


def test_flag_unknown_bike_double_mention_in_one_chat_is_one_row(
    chat_ctx: tools.ToolContext,
) -> None:
    first = _execute(flag_unknown_bike.NAME, chat_ctx, {"name": "Voge 500R AC"})
    second = _execute(flag_unknown_bike.NAME, chat_ctx, {"name": "Voge 500R AC"})

    assert first["status"] == "queued"
    assert second["status"] == "already_known"
    assert len(chat_ctx.session.rows(Motorbike)) == 1


def test_flag_unknown_bike_dedup_reaches_via_duplicate_model_error(
    chat_ctx: tools.ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tool's `already_known` branch is reached specifically through
    `product_service.DuplicateModelError` — not via a pre-check the tool invents.
    """
    calls: list[str] = []

    async def fake_create_backlog(session: object, name: str) -> Motorbike:
        calls.append(name)
        raise product_service.DuplicateModelError(name)

    monkeypatch.setattr(product_service, "create_backlog", fake_create_backlog)

    payload = _execute(flag_unknown_bike.NAME, chat_ctx, {"name": "Anything At All"})

    assert calls == ["Anything At All"]
    assert payload["status"] == "already_known"


# --- 5. the documented residual case --------------------------------------------


def test_a_differently_spaced_name_creates_a_separate_backlog_row(
    chat_ctx: tools.ToolContext,
) -> None:
    """Pinned boundary (not a bug): different slug ⇒ different entry.

    "Suzuki GSR600" and "Suzuki GSR 600" slugify differently, so the second
    mention is *not* deduplicated against the first — the tool invents no
    fuzzier identity than the catalogue's own slug.
    """
    asyncio.run(product_service.create_backlog(chat_ctx.session, "Suzuki GSR600"))

    payload = _execute(flag_unknown_bike.NAME, chat_ctx, {"name": "Suzuki GSR 600"})

    assert payload["status"] == "queued"
    slugs = sorted(row.slug for row in chat_ctx.session.rows(Motorbike))
    assert slugs == ["suzuki-gsr-600", "suzuki-gsr600"]


# --- 3. registry composition and write-tool policy ------------------------------


def test_registry_is_exactly_the_pinned_eight_tools_in_the_pinned_order() -> None:
    assert tools.tool_names() == [
        "catalogue_search",
        "spec_comparison",
        "licence_fit_check",
        "cost_estimator",
        "retrieve_bike_knowledge",
        "record_preference",
        "flag_unknown_bike",
        "present_recommendations",
    ]


def test_registry_order_is_stable_across_repeated_calls() -> None:
    assert tools.tool_names() == tools.tool_names()
    assert [spec.name for spec in tools.tool_specs()] == [spec.name for spec in tools.tool_specs()]


# Tokens whose presence in a tool module's source is evidence the tool performs a
# database write (as opposed to a read-only lookup through a service). Grepped
# rather than executed, because most of the six read tools have no meaningful
# write path to exercise at all — the point is to enumerate what *could* write,
# not merely what one test happened to trigger.
_WRITE_EVIDENCE = (
    "session.add(",
    "session.delete(",
    "product_service.create_backlog",
    "product_service.update_status",
    "product_service.create_motorbike",
    "chat_service.record_preference",
    "chat_service.append_",
)

_EXPECTED_WRITERS = {"record_preference", "flag_unknown_bike"}


def test_exactly_the_two_pinned_tools_contain_database_write_evidence() -> None:
    """Enumerate all 8 registered tool modules and classify each by source content.

    `present_recommendations` writes to the turn's collector (not the database);
    the four lookup tools and `retrieve_bike_knowledge` call read-only service
    functions. Only `record_preference` and `flag_unknown_bike` may contain a
    write marker — a third one appearing would be an undocumented write tool and
    should fail this test.
    """
    writers: set[str] = set()
    for spec in tools.tool_specs():
        module = inspect.getmodule(spec.run)
        assert module is not None and module.__file__ is not None
        source = Path(module.__file__).read_text()
        if any(marker in source for marker in _WRITE_EVIDENCE):
            writers.add(spec.name)

    assert writers == _EXPECTED_WRITERS


def test_no_extra_tool_module_exists_beyond_the_eight_registered_ones() -> None:
    """The tools package directory holds no orphaned/unregistered tool file."""
    registered = set(tools.tool_names())
    module_files = {
        path.stem for path in TOOLS_PACKAGE_DIR.glob("*.py") if path.stem not in {"__init__"}
    }
    # Every registered tool's module file exists...
    assert registered <= module_files
    # ...and no module file exists that is not a registered tool (mirrors the
    # naming convention `NAME = "<module_stem>"` every tool module follows).
    assert module_files <= registered


# --- 4. prompt block: consent-gated flagging + preference rendering ------------


def test_prompt_instructs_consent_gated_flagging(chat_ctx: tools.ToolContext) -> None:
    """The model must offer, then wait for a yes, before calling `flag_unknown_bike`."""
    assert chat_ctx.chat is not None
    # A non-empty history renders the "continue the interview" branch — the only
    # turn kind in which a flag can happen at all.
    history = [
        asyncio.run(
            chat_service.append_user_message(
                chat_ctx.session, chat_ctx.chat, "What about the Kawasaki Z650?"
            )
        )
    ]
    system_prompt = advisor.build_context(history=history, preferences=[])[0].text

    assert "flag_unknown_bike" in system_prompt
    # Line breaks are Markdown wrapping, not meaning: match whole sentences.
    lowered = " ".join(system_prompt.lower().split())
    # The offer-then-consent phrasing, not an unconditional instruction to flag.
    # Step 3.16 sharpened the wording after the model flagged unprompted: the
    # offer and the call now have to sit in two different turns.
    assert "ask** whether they would like the model noted" in lowered
    assert "the call only after the customer has answered yes in a later message" in lowered
    assert "without that yes, do not call it" in lowered


def test_prompt_renders_the_active_preferences_block_directly(
    chat_ctx: tools.ToolContext,
) -> None:
    """A focused proof of criterion 4, independent of the full agent loop: capture
    through the tool, then rebuild the context straight from the stored rows and
    check the active preference block — not merely that the loop test passed.
    """
    # Deliberately not "around 6000 €" for either capture: that exact string
    # already appears as an in-prompt instructional example (advisor_system.md's
    # `value` bullet), which would make the "did not leak" assertion below a
    # false negative regardless of what the tool actually rendered.
    assert chat_ctx.chat is not None
    _execute(
        record_preference.NAME,
        chat_ctx,
        {"attribute": "budget", "value": "roughly 6300 euros", "firmness": "soft"},
    )
    _execute(
        record_preference.NAME,
        chat_ctx,
        {"attribute": "budget", "value": "hard ceiling 5000 euros", "firmness": "hard"},
    )

    active = asyncio.run(chat_service.active_preferences(chat_ctx.session, chat_ctx.chat.id))
    system_prompt = advisor.build_context(history=[], preferences=active)[0].text

    assert "budget" in system_prompt
    assert "hard ceiling 5000 euros" in system_prompt
    assert "must-have" in system_prompt
    # The superseded value must not leak into the next rebuild.
    assert "roughly 6300 euros" not in system_prompt
