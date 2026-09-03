"""QA independent verification of step 3.12 (domain tools II) — the full agent
path: `execute()` → `resolve_references` → `fit_check_service` /
`cost_estimator_service`, the exact code both `app tools run` and the advisor
loop go through.

Distinct from the dev's `test_tools.py`: proves the A2 boundaries and the
"never a guessed value" rule through the *tool* layer (args schema included,
not the bare service function), validates both new result shapes — and their
`unknownBike` fallback — against the frozen read-path `ToolCall` schema,
re-runs the 3.11 no-SQL/registry conventions against the two new modules
specifically (and against the two new services, since the architecture's rule
is `agent tool → application service → database`, not a shortcut at the
service layer), and proves the camelCase StrEnum-inlining claim recorded in
this step's Landed decisions.

No test opens a database or reaches OpenRouter: the "session" is an inert
marker (the tools issue no statement of their own).
"""

import ast
import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ValidationError

from app.api.schemas.chat_messages import ToolCall
from app.db.models.motorbike import MotorbikeStatus
from app.llm.agents import tools
from app.llm.agents.tools import (
    catalogue_search,
    cost_estimator,
    licence_fit_check,
    spec_comparison,
)
from app.services import (
    catalogue_search_service,
    cost_data,
    cost_estimator_service,
    fit_check_service,
    product_service,
)
from app.services.catalogue_search_service import COMPARISON_SPEC_FIELDS, VerifiedSpecs
from app.services.naming_service import NameParts

BIKE_A = "01J0QATOOL000000000000AA"
BIKE_B = "01J0QATOOL000000000000BB"

_SQL_NAMES = {"select", "text", "insert", "update", "delete"}


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


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch) -> Any:
    class _Recorder:
        def __init__(self) -> None:
            self.specs: list[VerifiedSpecs] = []
            self.by_name: dict[str, _Motorbike] = {}
            self.by_id: dict[str, _Motorbike] = {}
            self.get_verified_specs_calls: list[list[str]] = []

    recorder = _Recorder()

    async def get_verified_specs(session: Any, motorbike_ids: Any) -> list[VerifiedSpecs]:
        recorder.get_verified_specs_calls.append(list(motorbike_ids))
        wanted = set(motorbike_ids)
        return [entry for entry in recorder.specs if entry.motorbike_id in wanted]

    async def resolve_name(session: Any, name: str) -> _Motorbike | None:
        return recorder.by_name.get(name)

    async def get_motorbike(session: Any, motorbike_id: str) -> _Motorbike | None:
        return recorder.by_id.get(motorbike_id)

    monkeypatch.setattr(catalogue_search_service, "get_verified_specs", get_verified_specs)
    monkeypatch.setattr(catalogue_search_service, "resolve_name", resolve_name)
    monkeypatch.setattr(product_service, "get_motorbike", get_motorbike)
    return recorder


@pytest.fixture
def ctx() -> tools.ToolContext:
    return tools.ToolContext(session=object())


def _approved(
    catalogue: Any, name: str = "Honda CB500F", motorbike_id: str = BIKE_A, **values: Any
) -> None:
    catalogue.by_name[name] = _Motorbike(motorbike_id, name, MotorbikeStatus.APPROVED)
    catalogue.by_id[motorbike_id] = catalogue.by_name[name]
    catalogue.specs = [*catalogue.specs, _specs(motorbike_id, name, **values)]


def _execute(name: str, ctx: tools.ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(tools.execute(tools.get_tool_spec(name), ctx, arguments))


# --- criterion 5: registry + convention, re-run against the two new modules -----


def test_both_new_tools_are_registered_after_the_311_tools_in_reading_order() -> None:
    # Step 3.13 appended `retrieve_bike_knowledge` and `present_recommendations`
    # behind these four; the 3.12 tools keep their reading-order position.
    assert tools.tool_names()[:4] == [
        catalogue_search.NAME,
        spec_comparison.NAME,
        licence_fit_check.NAME,
        cost_estimator.NAME,
    ]
    built = {tool.name for tool in tools.build_advisor_tools(tools.ToolContext(session=object()))}
    assert {licence_fit_check.NAME, cost_estimator.NAME} <= built


def test_neither_new_tool_module_constructs_sql() -> None:
    tools_dir = Path(licence_fit_check.__file__).parent
    for path in (tools_dir / "licence_fit_check.py", tools_dir / "cost_estimator.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "sqlalchemy" in node.module:
                offending = {alias.name for alias in node.names} & _SQL_NAMES
                assert not offending, f"{path.name} imports SQL verbs {offending} from sqlalchemy"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in _SQL_NAMES, (
                    f"{path.name} calls {node.func.id}(...) directly"
                )


def test_neither_new_service_module_constructs_sql_or_reaches_an_orm_model() -> None:
    """`agent tool → application service → database` is not a shortcut at the
    service layer either: both services may only reach `catalogue_search_service`
    (and, for fit checks, `product_service`'s A2 constants / `cost_data`'s table).
    Step 6.19 adds `naming_service` to the allowed set: both services render
    their result's `name` from `entry.parts` now (`render_name`, which itself
    performs no query — see its own module docstring), so this is still "no SQL,
    no ORM model", just one more pure-function import.
    """
    allowed_service_imports = {
        "catalogue_search_service",
        "product_service",
        "cost_data",
        "naming_service",
    }
    for module in (fit_check_service, cost_estimator_service):
        tree = ast.parse(Path(module.__file__).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            assert "app.db.models" not in node.module, f"{module.__name__} imports an ORM model"
            if node.module == "app.services":
                names = {alias.name for alias in node.names}
                assert names <= allowed_service_imports, f"{module.__name__} reaches {names}"
            if "sqlalchemy" in node.module:
                offending = {alias.name for alias in node.names} & _SQL_NAMES
                assert not offending, f"{module.__name__} imports SQL verbs {offending}"


# --- criterion 1: frozen shapes, validated against the read-path schema --------


def test_licence_fit_check_result_and_unknown_bike_both_validate(ctx: Any, catalogue: Any) -> None:
    _approved(catalogue, power_kw=35.0, wet_weight_kg=189.0, seat_height_mm=789)

    ok = _execute(licence_fit_check.NAME, ctx, {"motorbikeName": "Honda CB500F"})
    assert set(ok) == {"motorbikeId", "name", "rules"}
    for rule in ok["rules"]:
        assert set(rule) == {"rule", "label", "verdict", "evidence"}
        assert rule["verdict"] in {"pass", "fail", "unknown"}

    unknown = _execute(licence_fit_check.NAME, ctx, {"motorbikeName": "Not A Real Bike"})
    assert unknown == {"unknownBike": "Not A Real Bike"}

    for entry in ctx.collector.tool_calls:
        validated = ToolCall.model_validate(entry)
        assert validated.status.value == "succeeded"


def test_cost_estimator_result_and_unknown_bike_both_validate(ctx: Any, catalogue: Any) -> None:
    _approved(catalogue, category="naked", engine_cc=471, power_kw=35.0, price_band="mid")

    ok = _execute(cost_estimator.NAME, ctx, {"motorbikeName": "Honda CB500F"})
    assert set(ok) == {
        "motorbikeId",
        "name",
        "currency",
        "lineItems",
        "total",
        "assumptions",
        "coefficientsVersion",
    }
    assert ok["currency"] == "EUR"

    unknown = _execute(cost_estimator.NAME, ctx, {"motorbikeName": "Not A Real Bike"})
    assert unknown == {"unknownBike": "Not A Real Bike"}

    for entry in ctx.collector.tool_calls:
        validated = ToolCall.model_validate(entry)
        assert validated.status.value == "succeeded"


# --- criterion 2/3: A2 boundaries and rider fit through the full tool path -----


def test_a2_power_boundary_exactly_35_passes_through_the_tool(ctx: Any, catalogue: Any) -> None:
    _approved(catalogue, power_kw=35.0, wet_weight_kg=200.0)
    payload = _execute(licence_fit_check.NAME, ctx, {"motorbikeName": "Honda CB500F"})
    rules = {r["rule"]: r for r in payload["rules"]}
    assert rules["a2_power"]["verdict"] == "pass"


def test_a2_power_boundary_just_above_35_fails_through_the_tool(ctx: Any, catalogue: Any) -> None:
    _approved(catalogue, power_kw=35.01, wet_weight_kg=200.0)
    payload = _execute(licence_fit_check.NAME, ctx, {"motorbikeName": "Honda CB500F"})
    rules = {r["rule"]: r for r in payload["rules"]}
    assert rules["a2_power"]["verdict"] == "fail"


def test_a2_ratio_boundary_exactly_point_two_passes_through_the_tool(
    ctx: Any, catalogue: Any
) -> None:
    _approved(catalogue, power_kw=30.0, wet_weight_kg=150.0)  # 30 / 150 == 0.2
    payload = _execute(licence_fit_check.NAME, ctx, {"motorbikeName": "Honda CB500F"})
    rules = {r["rule"]: r for r in payload["rules"]}
    assert rules["a2_power_to_weight"]["verdict"] == "pass"


def test_a2_ratio_boundary_just_above_point_two_fails_through_the_tool(
    ctx: Any, catalogue: Any
) -> None:
    _approved(catalogue, power_kw=30.0, wet_weight_kg=149.0)  # 30 / 149 ≈ 0.2013
    payload = _execute(licence_fit_check.NAME, ctx, {"motorbikeName": "Honda CB500F"})
    rules = {r["rule"]: r for r in payload["rules"]}
    assert rules["a2_power_to_weight"]["verdict"] == "fail"


def test_missing_power_is_unknown_never_a_guessed_verdict_through_the_tool(
    ctx: Any, catalogue: Any
) -> None:
    _approved(catalogue, wet_weight_kg=190.0)  # no power_kw at all
    payload = _execute(licence_fit_check.NAME, ctx, {"motorbikeName": "Honda CB500F"})
    rules = {r["rule"]: r for r in payload["rules"]}
    assert rules["a2_power"]["verdict"] == "unknown"
    assert "no verified power" in rules["a2_power"]["evidence"]
    assert rules["a2_power_to_weight"]["verdict"] == "unknown"


def test_seat_height_estimate_discloses_estimation_through_the_tool(
    ctx: Any, catalogue: Any
) -> None:
    _approved(catalogue, seat_height_mm=800)
    payload = _execute(
        licence_fit_check.NAME, ctx, {"motorbikeName": "Honda CB500F", "riderHeightCm": 175}
    )
    rules = {r["rule"]: r for r in payload["rules"]}
    assert rules["seat_height_fit"]["verdict"] in {"pass", "fail"}
    assert "estimated" in rules["seat_height_fit"]["evidence"]


def test_weight_fit_is_unknown_without_experience_through_the_tool(
    ctx: Any, catalogue: Any
) -> None:
    _approved(catalogue, wet_weight_kg=190.0)
    payload = _execute(licence_fit_check.NAME, ctx, {"motorbikeName": "Honda CB500F"})
    rules = {r["rule"]: r for r in payload["rules"]}
    assert rules["weight_fit"]["verdict"] == "unknown"
    assert "experience level was not given" in rules["weight_fit"]["evidence"]


# --- criterion 4: determinism and the no-purchase-price path through the tool --


def test_cost_estimator_is_deterministic_and_total_is_the_sum_through_the_tool(
    ctx: Any, catalogue: Any
) -> None:
    _approved(catalogue, category="naked", engine_cc=471, power_kw=35.0, price_band="mid")
    arguments = {"motorbikeName": "Honda CB500F", "annualKm": 9500}

    first = _execute(cost_estimator.NAME, ctx, arguments)
    second = _execute(cost_estimator.NAME, ctx, arguments)

    assert first == second
    assert first["total"] == sum(line["amount"] for line in first["lineItems"])


def test_assumptions_are_never_empty_when_no_purchase_price_can_be_shown(
    ctx: Any, catalogue: Any
) -> None:
    """The dev-DB-live gap this step's Landed decisions call out."""
    _approved(catalogue, category="naked", engine_cc=471, power_kw=35.0)  # no msrp, no price_band
    payload = _execute(cost_estimator.NAME, ctx, {"motorbikeName": "Honda CB500F"})

    assert "Purchase price" not in {line["label"] for line in payload["lineItems"]}
    assert payload["assumptions"]
    assert payload["coefficientsVersion"] == cost_data.COEFFICIENTS_VERSION


# --- criterion 6: approved-only, single-read-seam enforcement ------------------


def test_an_unapproved_id_answers_unknown_bike_for_both_new_tools(ctx: Any, catalogue: Any) -> None:
    catalogue.by_id[BIKE_B] = _Motorbike(BIKE_B, "Backlog Bike", MotorbikeStatus.BACKLOG)

    assert _execute(licence_fit_check.NAME, ctx, {"motorbikeId": BIKE_B}) == {"unknownBike": BIKE_B}
    assert _execute(cost_estimator.NAME, ctx, {"motorbikeId": BIKE_B}) == {"unknownBike": BIKE_B}


def test_the_only_read_either_new_tool_triggers_is_get_verified_specs_by_id(
    ctx: Any, catalogue: Any
) -> None:
    _approved(catalogue, power_kw=35.0, wet_weight_kg=189.0)

    _execute(licence_fit_check.NAME, ctx, {"motorbikeName": "Honda CB500F"})
    assert catalogue.get_verified_specs_calls == [[BIKE_A]]

    catalogue.get_verified_specs_calls.clear()
    _execute(cost_estimator.NAME, ctx, {"motorbikeName": "Honda CB500F"})
    assert catalogue.get_verified_specs_calls == [[BIKE_A]]


# --- criterion 5: args validation at the single boundary, camelCase, enums -----


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"motorbikeName": "Honda CB500F", "riderHeightCm": 300},
        {"motorbikeName": "Honda CB500F", "licence": "A1"},
    ],
    ids=["no-bike", "height-out-of-range", "unsupported-a1"],
)
def test_licence_fit_check_bad_arguments_never_execute_or_get_recorded(
    ctx: Any, catalogue: Any, arguments: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        _execute(licence_fit_check.NAME, ctx, arguments)
    assert ctx.collector.tool_calls == []


@pytest.mark.parametrize(
    "arguments",
    [{}, {"motorbikeName": "Honda CB500F", "annualKm": 100000}],
    ids=["no-bike", "mileage-out-of-range"],
)
def test_cost_estimator_bad_arguments_never_execute_or_get_recorded(
    ctx: Any, catalogue: Any, arguments: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        _execute(cost_estimator.NAME, ctx, arguments)
    assert ctx.collector.tool_calls == []


def test_licence_and_experience_enums_are_inlined_camelcase_with_no_defs_or_ref(ctx: Any) -> None:
    """The Landed-decisions claim: LangChain inlines both StrEnums into the
    function schema (no `$defs`/`$ref` reaching the provider) — proven against
    what `convert_to_openai_tool` actually produces for the built tool.
    """
    built = {tool.name: tool for tool in tools.build_advisor_tools(ctx)}
    fit_schema = convert_to_openai_tool(built[licence_fit_check.NAME])["function"]
    cost_schema = convert_to_openai_tool(built[cost_estimator.NAME])["function"]

    for schema in (fit_schema, cost_schema):
        raw = json.dumps(schema["parameters"])
        assert "$defs" not in raw
        assert "$ref" not in raw
        for key in schema["parameters"]["properties"]:
            assert "_" not in key, f"{key} reached the provider snake_case"

    assert fit_schema["parameters"]["properties"]["licence"]["enum"] == ["A2", "A"]
    experience_raw = json.dumps(fit_schema["parameters"]["properties"]["experience"])
    assert "beginner" in experience_raw
    assert "returning" in experience_raw
    assert "experienced" in experience_raw
