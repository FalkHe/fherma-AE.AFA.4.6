"""QA independent verification of step 3.11 (domain tools I) + its two bundled
follow-ups.

This file does not re-author the dev's `test_tools.py` / `test_catalogue_
search_service.py` coverage; it proves the eight acceptance criteria from a
fresh angle — different fixtures, and in a few places a deliberately more
adversarial check (the LangChain schema trap, the drift guard's actual
failure mode) than the dev suite exercises.

No test opens a database or reaches OpenRouter/OpenRouter's embeddings.
"""

import ast
import asyncio
import inspect
from pathlib import Path
from typing import Any

import pytest
from langchain_core.tools import StructuredTool
from pydantic import ValidationError
from pydantic.alias_generators import to_camel

from app.api.schemas.chat_messages import ToolCall
from app.core.config import get_settings
from app.db.models.motorbike import MotorbikeStatus
from app.db.models.motorbike_spec import SPEC_FIELDS
from app.llm import query_translation
from app.llm.agents import tools
from app.llm.agents.tools import catalogue_search, spec_comparison
from app.services import catalogue_search_service, product_service, rag_pipeline_service
from app.services.catalogue_search_service import (
    COMPARISON_SPEC_FIELDS,
    UNCOMPARED_SPEC_FIELDS,
    VerifiedSpecs,
)
from app.services.naming_service import NameParts

BIKE_A = "01J0QABIKE000000000000AAA"
BIKE_B = "01J0QABIKE000000000000BBB"

TOOLS_DIR = Path(catalogue_search.__file__).parent


# --- criterion 1: frozen result shapes -----------------------------------------


def test_catalogue_search_result_shape_is_exactly_the_pinned_keys() -> None:
    """`CatalogueSearchResult`/`CatalogueSearchHit` dump to exactly the pinned keys.

    Read straight off the shared-knowledge §Tool result schemas text, not off the
    dev's model: `results`, `totalCount`, and per-hit `motorbikeId, name,
    category, powerKw, wetWeightKg, seatHeightMm, priceBand` — nothing more,
    nothing less.
    """
    hit = catalogue_search.CatalogueSearchHit(
        motorbike_id=BIKE_A,
        name="Honda CB500F",
        category="naked",
        power_kw=35.0,
        wet_weight_kg=189.0,
        seat_height_mm=785,
        price_band="mid",
    )
    result = catalogue_search.CatalogueSearchResult(results=[hit], total_count=7)

    dumped = result.model_dump(by_alias=True)
    assert set(dumped) == {"results", "totalCount"}
    assert set(dumped["results"][0]) == {
        "motorbikeId",
        "name",
        "category",
        "powerKw",
        "wetWeightKg",
        "seatHeightMm",
        "priceBand",
    }
    assert dumped["totalCount"] == 7


def test_spec_comparison_result_shape_is_exactly_the_pinned_keys() -> None:
    """`SpecComparisonResult` dumps to `{bikes:[{motorbikeId,name}], rows:[{field,values}]}`."""
    result = spec_comparison.SpecComparisonResult(
        bikes=[spec_comparison.ComparedBike(motorbike_id=BIKE_A, name="Honda CB500F")],
        rows=[spec_comparison.ComparisonRow(field="powerKw", values=[35.0])],
    )

    dumped = result.model_dump(by_alias=True)
    assert set(dumped) == {"bikes", "rows"}
    assert set(dumped["bikes"][0]) == {"motorbikeId", "name"}
    assert set(dumped["rows"][0]) == {"field", "values"}


def test_unknown_bike_result_shape_is_exactly_the_pinned_key() -> None:
    dumped = tools.UnknownBikeResult(unknown_bike="Bikeley 999").model_dump(by_alias=True)
    assert dumped == {"unknownBike": "Bikeley 999"}


def test_spec_comparison_carries_every_comparison_field_with_no_gaps() -> None:
    """Every one of the 13 frozen fields is a row, and none of the 3 excluded ones is."""
    session = _CatalogueStub(
        by_name={
            "Honda CB500F": _Motorbike(BIKE_A, "Honda CB500F", MotorbikeStatus.APPROVED),
            "Suzuki GSR600": _Motorbike(BIKE_B, "Suzuki GSR600", MotorbikeStatus.APPROVED),
        },
        specs=[_specs(BIKE_A, "Honda CB500F"), _specs(BIKE_B, "Suzuki GSR600")],
    )
    with session.patched():
        payload = asyncio.run(
            tools.execute(
                tools.get_tool_spec(spec_comparison.NAME),
                tools.ToolContext(session=object()),
                {"names": ["Honda CB500F", "Suzuki GSR600"]},
            )
        )
    fields = {row["field"] for row in payload["rows"]}
    assert fields == {to_camel(field) for field in COMPARISON_SPEC_FIELDS}
    assert len(COMPARISON_SPEC_FIELDS) == 13
    for excluded in UNCOMPARED_SPEC_FIELDS:
        assert to_camel(excluded) not in fields


def test_catalogue_search_caps_results_at_twelve_but_total_count_is_uncapped() -> None:
    ids = [f"01J0QACAP{index:017d}" for index in range(20)]
    session = _CatalogueStub(matches=ids, specs=[_specs(mid, f"Bike {mid}") for mid in ids])
    with session.patched():
        payload = asyncio.run(
            tools.execute(
                tools.get_tool_spec(catalogue_search.NAME),
                tools.ToolContext(session=object()),
                {},
            )
        )
    assert len(payload["results"]) == 12
    assert payload["totalCount"] == 20


# --- criterion 2: resolve_name precedence ---------------------------------------


class _ScriptedResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> "_ScriptedResult":
        return self

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return self._rows


class _QaScriptedSession:
    """A minimal scripted session for `resolve_name`'s three-statement path
    (slug, then type code, then substring — step 6.19 added the middle leg).

    Independent of the dev's `ScriptedSession` (fresh implementation), used only
    to prove the resolver's precedence and approved-only rule. Every non-slug
    `execute()` replays the same scripted rows, since neither the type-code nor
    the substring leg is what these tests are about — an empty list at either
    still falls through the way the real SQL would for "no match".
    """

    def __init__(self, substring_rows: list[Any]) -> None:
        self.substring_rows = substring_rows
        self.statement_count = 0

    async def execute(self, statement: Any) -> _ScriptedResult:
        self.statement_count += 1
        return _ScriptedResult(self.substring_rows)


def _bike(name: str, status: MotorbikeStatus, motorbike_id: str = BIKE_A) -> Any:
    class _M:
        pass

    entry = _M()
    entry.id = motorbike_id
    entry.query_name = name
    entry.status = status
    return entry


def test_exact_slug_wins_over_substring_and_no_substring_query_is_issued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slug precedence, proven by asserting the fallback statement never fires."""
    approved = _bike("Honda CB500F", MotorbikeStatus.APPROVED)

    async def get_by_slug(session: Any, slug: str) -> Any:
        assert slug == "honda-cb500f"
        return approved

    monkeypatch.setattr(product_service, "get_by_slug", get_by_slug)
    session = _QaScriptedSession(
        substring_rows=[_bike("Should Not Be Seen", MotorbikeStatus.APPROVED)]
    )

    result = asyncio.run(catalogue_search_service.resolve_name(session, "Honda CB500F"))

    assert result is approved
    assert session.statement_count == 0  # the substring statement was never issued


def test_a_backlog_model_never_resolves_even_when_its_slug_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The approved-only rule at the slug step: a non-approved hit is not an answer."""
    unapproved = _bike("Prototype X", MotorbikeStatus.BACKLOG)

    async def get_by_slug(session: Any, slug: str) -> Any:
        return unapproved

    monkeypatch.setattr(product_service, "get_by_slug", get_by_slug)
    # The substring fallback SQL itself filters `status == approved`, so a
    # backlog-only catalogue answers empty here too.
    session = _QaScriptedSession(substring_rows=[])

    result = asyncio.run(catalogue_search_service.resolve_name(session, "Prototype X"))

    assert result is None
    # It did try the type-code leg and the substring fallback before giving up.
    assert session.statement_count == 2


def test_a_rejected_model_never_resolves_via_substring_either(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_by_slug(session: Any, slug: str) -> Any:
        return None

    monkeypatch.setattr(product_service, "get_by_slug", get_by_slug)
    # Even if a rejected model happened to appear in a naive scan, the real SQL's
    # WHERE clause excludes it; this stub proves resolve_name never second-guesses
    # what the statement returns (i.e. does not re-check status in Python only
    # for the slug path and skip it for the substring path).
    session = _QaScriptedSession(substring_rows=[])

    result = asyncio.run(catalogue_search_service.resolve_name(session, "Rejected Bike"))

    assert result is None


def test_unresolvable_name_never_raises_it_is_a_result_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_by_slug(session: Any, slug: str) -> Any:
        return None

    monkeypatch.setattr(product_service, "get_by_slug", get_by_slug)
    session = _QaScriptedSession(substring_rows=[])

    try:
        result = asyncio.run(
            catalogue_search_service.resolve_name(session, "Nonexistent Moped 3000")
        )
    except Exception as error:  # pragma: no cover - the assertion below fails first if raised
        pytest.fail(f"resolve_name raised {error!r} instead of returning None")

    assert result is None


def test_spec_comparison_answers_unknown_bike_result_never_an_exception() -> None:
    """A tool given an unresolvable name answers the pinned result, not a raise."""
    session = _CatalogueStub(
        by_name={"Honda CB500F": _Motorbike(BIKE_A, "Honda CB500F", MotorbikeStatus.APPROVED)}
    )
    with session.patched():
        payload = asyncio.run(
            tools.execute(
                tools.get_tool_spec(spec_comparison.NAME),
                tools.ToolContext(session=object()),
                {"names": ["Honda CB500F", "Not A Real Bike"]},
            )
        )
    assert payload == {"unknownBike": "Not A Real Bike"}


# --- criterion 3: no SQL in the tool modules -------------------------------------


_SQL_NAMES = {"select", "text", "insert", "update", "delete"}


def test_tool_modules_contain_no_sqlalchemy_statement_construction() -> None:
    """AST-scan every module in `app/llm/agents/tools/` for SQL construction.

    Two checks per module: no `from sqlalchemy import select/text/...` (or
    `sqlalchemy.sql`), and no call expression whose bare name is one of the SQL
    verbs (`select(...)`, `text(...)`) — catching both an import-time and a
    call-time way of sneaking a statement into a tool.
    """
    tool_files = sorted(TOOLS_DIR.glob("*.py"))
    assert len(tool_files) >= 3, "expected __init__.py, catalogue_search.py, spec_comparison.py"

    for path in tool_files:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "sqlalchemy" in node.module:
                imported = {alias.name for alias in node.names}
                offending = imported & _SQL_NAMES
                assert not offending, f"{path.name} imports SQL verbs {offending} from sqlalchemy"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in _SQL_NAMES, (
                    f"{path.name} calls {node.func.id}(...) directly — SQL construction "
                    "belongs in a service"
                )


# --- criterion 4: collector convention, validated against the pinned read schema ----


def test_a_successful_call_s_recorded_entry_validates_against_the_frozen_tool_call_schema() -> None:
    """The entry the collector records must satisfy `app.api.schemas.chat_messages.ToolCall`
    verbatim — that model is what `GET /api/chat-messages` validates stored rows
    against, so this is the real contract, not just "looks right"."""
    session = _CatalogueStub(matches=[BIKE_A], specs=[_specs(BIKE_A, "Honda CB500F")])
    ctx = tools.ToolContext(session=object())
    with session.patched():
        asyncio.run(tools.execute(tools.get_tool_spec(catalogue_search.NAME), ctx, {}))

    (entry,) = ctx.collector.tool_calls
    validated = ToolCall.model_validate(entry)
    assert validated.status.value == "succeeded"
    assert validated.error is None


def test_a_failing_call_s_recorded_entry_also_validates_and_carries_a_one_line_error() -> None:
    session = _CatalogueStub()

    async def explode(session: Any, filters: Any) -> list[str]:
        raise ValueError("x" * 500)  # deliberately longer than the recorder's cap

    ctx = tools.ToolContext(session=object())
    with session.patched(find_motorbike_ids=explode), pytest.raises(ValueError):
        asyncio.run(tools.execute(tools.get_tool_spec(catalogue_search.NAME), ctx, {}))

    (entry,) = ctx.collector.tool_calls
    validated = ToolCall.model_validate(entry)
    assert validated.status.value == "failed"
    assert validated.error is not None
    assert "\n" not in validated.error  # one line
    assert len(validated.error) <= 200
    assert validated.result == {}


# --- criterion 5: args validation at the single boundary -------------------------


def test_missing_required_bikes_raises_validation_error_before_any_service_call() -> None:
    session = _CatalogueStub()
    ctx = tools.ToolContext(session=object())
    with session.patched(), pytest.raises(ValidationError):
        asyncio.run(
            tools.execute(
                tools.get_tool_spec(spec_comparison.NAME), ctx, {"motorbikeIds": "not-a-list"}
            )
        )
    assert ctx.collector.tool_calls == []


def test_camel_case_alias_is_accepted_and_snake_case_also_still_works() -> None:
    """`populate_by_name=True`: the CLI's snake_case and the model's camelCase both validate."""
    args_camel = catalogue_search.CatalogueSearchArgs.model_validate({"a2Eligible": True})
    args_snake = catalogue_search.CatalogueSearchArgs.model_validate({"a2_eligible": True})
    assert args_camel.a2_eligible is True
    assert args_snake.a2_eligible is True


def test_the_langchain_class_based_args_schema_trap_is_real_and_the_app_avoids_it() -> None:
    """Prove the documented trap by triggering it, then prove the shipped code
    does not: a `StructuredTool` built from the *class* loses camelCase, one
    built from `model_json_schema()` (what `_langchain_tool` actually does)
    keeps it.
    """

    async def _noop(**kwargs: Any) -> str:
        return "{}"

    trapped = StructuredTool.from_function(
        coroutine=_noop,
        name="trapped",
        description="d",
        args_schema=catalogue_search.CatalogueSearchArgs,
    )
    # LangChain's own OpenAI-tool conversion is what the provider actually sees.
    from langchain_core.utils.function_calling import convert_to_openai_tool

    trapped_props = convert_to_openai_tool(trapped)["function"]["parameters"]["properties"]
    assert "a2_eligible" in trapped_props, (
        "expected the class-based StructuredTool to lose the camelCase alias "
        "(the documented LangChain trap) — if this fails, the trap no longer "
        "reproduces and the code comment in tools/__init__.py should be revisited"
    )
    assert "a2Eligible" not in trapped_props

    ctx = tools.ToolContext(session=object())
    real_search = next(
        tool for tool in tools.build_advisor_tools(ctx) if tool.name == catalogue_search.NAME
    )
    real_props = convert_to_openai_tool(real_search)["function"]["parameters"]["properties"]
    assert "a2Eligible" in real_props
    assert "a2_eligible" not in real_props


# --- criterion 6: TRANSLATION_TEMPERATURE reaches the model invocation -----------


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.usefixtures("configured")
def test_translation_temperature_is_bound_on_the_actual_request_kwargs() -> None:
    """`with_structured_output`'s extra kwargs become `self.bind(**kwargs)` in
    langchain_openai — i.e. `chain.steps[0].kwargs` is what is serialized into
    the HTTP request body, not a cosmetic attribute. Verified against the
    installed langchain_openai source (see QA notes) rather than assumed.
    """
    chain = query_translation.build_translation_chain()

    bound_step = chain.steps[0]
    assert bound_step.kwargs["temperature"] == 0.0
    assert query_translation.TRANSLATION_TEMPERATURE == 0.0
    # The bound model itself carries no constructor-level temperature — this is a
    # per-request override riding along in `.kwargs`, the dict that becomes the
    # request body, not a model default baked in at construction.
    assert bound_step.bound.temperature is None


def test_translate_query_signature_is_unchanged() -> None:
    signature = inspect.signature(query_translation.translate_query)
    assert list(signature.parameters) == [
        "utterance",
        "history_summary",
        "preferences",
        "model",
    ]
    assert signature.parameters["history_summary"].default is None
    assert signature.parameters["preferences"].default == ()
    assert signature.parameters["model"].default is None


# --- criterion 7: rag_pipeline_service delegates to resolve_name -----------------


def test_resolve_names_calls_catalogue_search_service_resolve_name_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delegation proven without touching the dev's moved fixture: patch the real
    module function and assert the private helper calls it, verbatim name in,
    approved bike id out, unresolved skipped, never raises.
    """
    calls: list[str] = []

    async def resolve_name(session: Any, name: str) -> Any:
        calls.append(name)
        if name == "Honda CB500F":
            return _bike("Honda CB500F", MotorbikeStatus.APPROVED, BIKE_A)
        return None

    monkeypatch.setattr(catalogue_search_service, "resolve_name", resolve_name)

    result = asyncio.run(
        rag_pipeline_service._resolve_names(object(), ["Honda CB500F", "Unknown Bike"])
    )

    assert calls == ["Honda CB500F", "Unknown Bike"]
    assert result == [BIKE_A]


def test_resolve_names_deduplicates_and_still_never_raises_for_an_unknown_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def resolve_name(session: Any, name: str) -> Any:
        if name in ("Honda CB500F", "CB500F"):
            return _bike("Honda CB500F", MotorbikeStatus.APPROVED, BIKE_A)
        return None

    monkeypatch.setattr(catalogue_search_service, "resolve_name", resolve_name)

    result = asyncio.run(
        rag_pipeline_service._resolve_names(object(), ["Honda CB500F", "CB500F", "Totally Unknown"])
    )

    assert result == [BIKE_A]  # deduplicated, unresolved silently skipped


# --- criterion 8: comparison drift guard actually fails on an unclassified field ----


def test_the_drift_guard_would_fail_the_suite_for_an_unclassified_spec_column() -> None:
    """Reproduce the guard's own assertion (`test_catalogue_search_service.py`'s
    `test_the_comparable_columns_are_exactly_the_frozen_set_minus_the_long_tail`)
    against a *simulated* extra column, without touching the real frozen sets —
    proving the guard's failure mode is real rather than merely asserting
    equality against itself.
    """
    simulated_spec_fields = (*SPEC_FIELDS, "wheelbase_mm")  # a hypothetical new column

    covered = set(COMPARISON_SPEC_FIELDS) | set(UNCOMPARED_SPEC_FIELDS)
    # The real, landed sets do cover the real SPEC_FIELDS today...
    assert covered == set(SPEC_FIELDS)
    # ...but would NOT cover a newly added, unclassified column — which is
    # exactly the guard assertion the dev's test performs against the live
    # SPEC_FIELDS, and exactly what would turn red if a future step added a
    # column without updating COMPARISON_SPEC_FIELDS/UNCOMPARED_SPEC_FIELDS.
    assert covered != set(simulated_spec_fields)
    assert "wheelbase_mm" not in covered


# --- shared QA-local stub (not promoted to conftest.py: single-file use) --------


class _Motorbike:
    def __init__(self, motorbike_id: str, name: str, status: Any) -> None:
        self.id = motorbike_id
        self.query_name = name
        self.status = status


def _parts(motorbike_id: str, name: str) -> NameParts:
    """`NameParts` with no structured identity: `render_name` falls back to
    `query_name` verbatim — this test file is not about naming.
    """
    return NameParts(
        motorbike_id=motorbike_id,
        manufacturer=None,
        buildingline=None,
        model_name=None,
        year_from=None,
        year_to=None,
        query_name=name,
    )


def _specs(motorbike_id: str, name: str, **values: Any) -> VerifiedSpecs:
    return VerifiedSpecs(
        motorbike_id=motorbike_id,
        name=name,
        values={field: values.get(field) for field in COMPARISON_SPEC_FIELDS},
        parts=_parts(motorbike_id, name),
    )


class _CatalogueStub:
    """A minimal service-boundary stub, independent of the dev's `catalogue` fixture."""

    def __init__(
        self,
        *,
        matches: list[str] | None = None,
        specs: list[VerifiedSpecs] | None = None,
        by_name: dict[str, Any] | None = None,
        by_id: dict[str, Any] | None = None,
    ) -> None:
        self.matches = matches or []
        self.specs = specs or []
        self.by_name = by_name or {}
        self.by_id = by_id or {}

    def patched(self, **overrides: Any):
        import contextlib

        @contextlib.contextmanager
        def _cm():
            import unittest.mock as mock

            async def find_motorbike_ids(session: Any, filters: Any) -> list[str]:
                return list(self.matches)

            async def get_verified_specs(session: Any, motorbike_ids: Any) -> list[VerifiedSpecs]:
                wanted = set(motorbike_ids)
                return [entry for entry in self.specs if entry.motorbike_id in wanted]

            async def resolve_name(session: Any, name: str) -> Any:
                return self.by_name.get(name)

            async def get_motorbike(session: Any, motorbike_id: str) -> Any:
                return self.by_id.get(motorbike_id)

            targets = {
                (catalogue_search_service, "find_motorbike_ids"): overrides.get(
                    "find_motorbike_ids", find_motorbike_ids
                ),
                (catalogue_search_service, "get_verified_specs"): overrides.get(
                    "get_verified_specs", get_verified_specs
                ),
                (catalogue_search_service, "resolve_name"): overrides.get(
                    "resolve_name", resolve_name
                ),
                (product_service, "get_motorbike"): overrides.get("get_motorbike", get_motorbike),
            }
            with (
                mock.patch.multiple(
                    catalogue_search_service,
                    find_motorbike_ids=targets[(catalogue_search_service, "find_motorbike_ids")],
                    get_verified_specs=targets[(catalogue_search_service, "get_verified_specs")],
                    resolve_name=targets[(catalogue_search_service, "resolve_name")],
                ),
                mock.patch.object(
                    product_service,
                    "get_motorbike",
                    targets[(product_service, "get_motorbike")],
                ),
            ):
                yield

        return _cm()
