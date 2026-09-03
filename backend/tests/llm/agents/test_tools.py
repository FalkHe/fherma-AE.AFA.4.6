"""`app/llm/agents/tools/` — the convention and the four tools of steps 3.11–3.12.

A tool is a thin mapping between the model and a service, so these tests stub the
services (`catalogue_search_service`, `product_service`; the fit-check and cost
services run for real on top of the stubbed catalogue read, because their own
modules own their arithmetic) and assert the things only the tool layer owns:

* **the frozen result shapes** — camelCase keys, the comparison covering every
  comparable specification field with explicit `null`s, the shortlist cap next to
  the true `totalCount`. The chat UI's renderers are written against these exact
  keys, so a rename must fail here;
* **name resolution failure** — `{"unknownBike": …}` instead of an exception;
* **args-schema validation** — a call the schema rejects never reaches a service
  and is not recorded, because it never executed;
* **capture** — the wrapper records every executed call in the pinned
  `tool_calls[]` shape, failures included, and hands the model a JSON string.

No test opens a database or reaches OpenRouter: the "session" is an inert marker
(the tools issue no statement of their own).
"""

import asyncio
import json
from typing import Any

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ValidationError
from pydantic.alias_generators import to_camel

from app.api.schemas.chat_messages import ToolCall
from app.db.models.motorbike import MotorbikeStatus
from app.llm.agents import tools
from app.llm.agents.tools import (
    catalogue_search,
    cost_estimator,
    flag_unknown_bike,
    licence_fit_check,
    present_recommendations,
    record_preference,
    retrieve_bike_knowledge,
    spec_comparison,
)
from app.llm.query_translation import SpecFilters
from app.services import catalogue_search_service, cost_data, product_service, rag_pipeline_service
from app.services.catalogue_search_service import COMPARISON_SPEC_FIELDS, VerifiedSpecs
from app.services.naming_service import NameParts
from app.services.rag_pipeline_service import RagResult
from app.services.retrieval_service import RetrievedChunk

BIKE_A = "01J0BIKE0000000000000000AA"
BIKE_B = "01J0BIKE0000000000000000BB"


class _Session:
    """Marker object: every statement is a stubbed service call away."""


class _Motorbike:
    """The three attributes the tool layer reads off a catalogue entry."""

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
    """One `get_verified_specs` entry: every comparable field, mostly unknown."""
    return VerifiedSpecs(
        motorbike_id=motorbike_id,
        name=name,
        values={field: values.get(field) for field in COMPARISON_SPEC_FIELDS},
        parts=_parts(motorbike_id, name),
    )


@pytest.fixture
def ctx() -> tools.ToolContext:
    """A tool context with a fresh collector and no chat (like the CLI harness)."""
    return tools.ToolContext(session=_Session())


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Replace the three service entry points the two tools use.

    Returns the recorder so a test can assert what the tool asked the service for
    — the filter object above all, since "the tool reuses the 3.8 filter surface"
    is only true if a `SpecFilters` arrives.
    """

    class _Recorder:
        def __init__(self) -> None:
            self.filters: list[SpecFilters] = []
            self.requested_ids: list[list[str]] = []
            self.matches: list[str] = []
            self.specs: list[VerifiedSpecs] = []
            self.by_name: dict[str, _Motorbike] = {}
            self.by_id: dict[str, _Motorbike] = {}

    recorder = _Recorder()

    async def find_motorbike_ids(session: Any, filters: SpecFilters) -> list[str]:
        recorder.filters.append(filters)
        return list(recorder.matches)

    async def get_verified_specs(session: Any, motorbike_ids: Any) -> list[VerifiedSpecs]:
        recorder.requested_ids.append(list(motorbike_ids))
        wanted = set(motorbike_ids)
        return [entry for entry in recorder.specs if entry.motorbike_id in wanted]

    async def resolve_name(session: Any, name: str) -> _Motorbike | None:
        return recorder.by_name.get(name)

    async def get_motorbike(session: Any, motorbike_id: str) -> _Motorbike | None:
        return recorder.by_id.get(motorbike_id)

    monkeypatch.setattr(catalogue_search_service, "find_motorbike_ids", find_motorbike_ids)
    monkeypatch.setattr(catalogue_search_service, "get_verified_specs", get_verified_specs)
    monkeypatch.setattr(catalogue_search_service, "resolve_name", resolve_name)
    monkeypatch.setattr(product_service, "get_motorbike", get_motorbike)
    return recorder


def _execute(name: str, ctx: tools.ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one registered tool the way the loop and the CLI both run it."""
    return asyncio.run(tools.execute(tools.get_tool_spec(name), ctx, arguments))


# --- the convention -----------------------------------------------------------


def test_the_registry_holds_this_step_s_tools_and_rejects_an_unknown_name() -> None:
    """`tool_names` is what the CLI lists and what the loop binds, in order."""
    assert tools.tool_names() == [
        catalogue_search.NAME,
        spec_comparison.NAME,
        licence_fit_check.NAME,
        cost_estimator.NAME,
        retrieve_bike_knowledge.NAME,
        record_preference.NAME,
        flag_unknown_bike.NAME,
        present_recommendations.NAME,
    ]
    with pytest.raises(KeyError):
        tools.get_tool_spec("book_a_test_ride")


def test_every_registered_tool_has_a_described_camel_aliased_args_schema() -> None:
    """The convention itself: a schema the model can be shown, camelCase keys.

    `populate_by_name` is what lets the CLI harness pass snake_case while the
    model sends camelCase, and the description is what the model decides on.
    """
    for spec in tools.tool_specs():
        assert spec.description.strip(), spec.name
        assert spec.args_schema.model_config.get("populate_by_name") is True, spec.name
        properties = spec.args_schema.model_json_schema()["properties"]
        assert properties, spec.name
        for key in properties:
            assert key == to_camel(key), f"{spec.name}.{key} is not camelCase"


def test_what_the_model_is_shown_carries_the_camel_case_arguments(
    ctx: tools.ToolContext,
) -> None:
    """The function schema the provider receives, not just the class's aliases.

    Handed a Pydantic `args_schema`, LangChain rebuilds a subset model and loses
    the aliases — so the tool is built from the schema *dict* instead, and this is
    the test that would catch a regression to the class.
    """
    schemas = {
        tool.name: convert_to_openai_tool(tool)["function"]
        for tool in tools.build_advisor_tools(ctx)
    }

    assert set(schemas) == set(tools.tool_names())
    for name, schema in schemas.items():
        assert schema["description"], name
        for key in schema["parameters"]["properties"]:
            assert key == to_camel(key), f"{name}.{key} reached the provider snake_case"
    assert "a2Eligible" in schemas[catalogue_search.NAME]["parameters"]["properties"]
    assert set(schemas[spec_comparison.NAME]["parameters"]["properties"]) == {
        "motorbikeIds",
        "names",
    }


def test_a_langchain_tool_returns_the_result_as_json_and_records_it(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """What the agent loop sees: a JSON string, plus the pinned collector entry."""
    catalogue.matches = [BIKE_A]
    catalogue.specs = [_specs(BIKE_A, "Honda CB500F", category="naked", power_kw=35.0)]

    search = next(
        tool for tool in tools.build_advisor_tools(ctx) if tool.name == catalogue_search.NAME
    )
    answer = asyncio.run(search.ainvoke({"a2Eligible": True}))

    assert json.loads(answer) == {
        "results": [
            {
                "motorbikeId": BIKE_A,
                "name": "Honda CB500F",
                "category": "naked",
                "powerKw": 35.0,
                "wetWeightKg": None,
                "seatHeightMm": None,
                "priceBand": None,
            }
        ],
        "totalCount": 1,
    }
    (entry,) = ctx.collector.tool_calls
    assert entry["tool"] == catalogue_search.NAME
    assert entry["status"] == "succeeded"
    assert entry["error"] is None
    assert len(entry["id"]) == 26
    # Arguments are recorded camelCase, as the persisted shape pins them.
    assert entry["arguments"]["a2Eligible"] is True
    assert entry["result"] == json.loads(answer)


def test_a_failing_tool_is_recorded_as_failed_and_reraised(
    ctx: tools.ToolContext, catalogue: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tool that raises must still be visible in the turn — and still raise.

    The loop needs the exception to tell the model what went wrong; the customer
    needs the entry to see that something was attempted.
    """

    async def explode(session: Any, filters: SpecFilters) -> list[str]:
        raise RuntimeError("connection lost")

    monkeypatch.setattr(catalogue_search_service, "find_motorbike_ids", explode)

    with pytest.raises(RuntimeError):
        _execute(catalogue_search.NAME, ctx, {})

    (entry,) = ctx.collector.tool_calls
    assert entry["status"] == "failed"
    assert entry["result"] == {}
    assert entry["error"] == "RuntimeError: connection lost"


# --- catalogue_search ---------------------------------------------------------


def test_catalogue_search_hands_the_service_the_frozen_filter_surface(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """The args schema *is* `SpecFilters` (3.8), normalizers included."""
    _execute(catalogue_search.NAME, ctx, {"seatHeightMmMax": "80 cm", "priceBands": ["Mid"]})

    (filters,) = catalogue.filters
    assert isinstance(filters, SpecFilters)
    assert filters.seat_height_mm_max == 800
    assert filters.values()["price_bands"] == ["mid"]


def test_catalogue_search_caps_the_shortlist_and_still_reports_every_match(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """The cap is a display cap: `totalCount` never shrinks with it."""
    ids = [f"01J0BIKE{index:018d}" for index in range(catalogue_search.MAX_RESULTS + 3)]
    catalogue.matches = ids
    catalogue.specs = [_specs(motorbike_id, f"Bike {motorbike_id}") for motorbike_id in ids]

    payload = _execute(catalogue_search.NAME, ctx, {})

    assert len(payload["results"]) == catalogue_search.MAX_RESULTS
    assert payload["totalCount"] == len(ids)
    # Only the visible ids were loaded — the cap is applied before the read.
    assert catalogue.requested_ids == [ids[: catalogue_search.MAX_RESULTS]]


def _named_parts(motorbike_id: str, **overrides: Any) -> NameParts:
    """A `NameParts` whose fields default to "no structured identity" so a test
    only has to state the fields its collision is actually about.
    """
    defaults: dict[str, Any] = {
        "motorbike_id": motorbike_id,
        "manufacturer": None,
        "buildingline": None,
        "model_name": None,
        "year_from": None,
        "year_to": None,
        "query_name": motorbike_id,
    }
    return NameParts(**(defaults | overrides))


def test_catalogue_search_names_escalate_only_under_a_colliding_context(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """`MODEL` is the pinned floor (D5): two rows sharing manufacturer and model
    in the *same result set* escalate to their year range; a third, non-colliding
    row in that same set stays short — and every pinned key survives unchanged.
    """
    bike_c = "01J0BIKE0000000000000000CC"
    catalogue.matches = [BIKE_A, BIKE_B, bike_c]
    empty_values = dict.fromkeys(COMPARISON_SPEC_FIELDS)
    catalogue.specs = [
        VerifiedSpecs(
            motorbike_id=BIKE_A,
            name="ignored",
            values=empty_values,
            parts=_named_parts(
                BIKE_A, manufacturer="BMW", model_name="R 1250 GS", year_from=2019, year_to=2023
            ),
        ),
        VerifiedSpecs(
            motorbike_id=BIKE_B,
            name="ignored",
            values=empty_values,
            parts=_named_parts(BIKE_B, manufacturer="BMW", model_name="R 1250 GS", year_from=2023),
        ),
        VerifiedSpecs(
            motorbike_id=bike_c,
            name="ignored",
            values=empty_values,
            parts=_named_parts(bike_c, manufacturer="Honda", model_name="CB500F", year_from=2019),
        ),
    ]

    payload = _execute(catalogue_search.NAME, ctx, {})

    names = {hit["motorbikeId"]: hit["name"] for hit in payload["results"]}
    assert names[BIKE_A] == "BMW R 1250 GS (2019–2023)"
    assert names[BIKE_B] == "BMW R 1250 GS (from 2023)"
    assert names[bike_c] == "Honda CB500F"
    for hit in payload["results"]:
        assert set(hit) == {
            "motorbikeId",
            "name",
            "category",
            "powerKw",
            "wetWeightKg",
            "seatHeightMm",
            "priceBand",
        }


# --- spec_comparison ----------------------------------------------------------


def test_spec_comparison_covers_every_comparable_field_with_aligned_values(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """The frozen table: one row per comparable field, values aligned to `bikes`.

    The second bike has no verified power at all, which is the case the project
    cares about — the cell is an explicit `null`, never a copy of the neighbour
    and never a guess.
    """
    catalogue.by_name = {
        "Honda CB500F": _Motorbike(BIKE_A, "Honda CB500F", MotorbikeStatus.APPROVED),
        "Suzuki GSR600": _Motorbike(BIKE_B, "Suzuki GSR600", MotorbikeStatus.APPROVED),
    }
    catalogue.specs = [
        _specs(BIKE_A, "Honda CB500F", category="naked", power_kw=35.0, a2_eligible=True),
        _specs(BIKE_B, "Suzuki GSR600", category="naked"),
    ]

    payload = _execute(spec_comparison.NAME, ctx, {"names": ["Honda CB500F", "Suzuki GSR600"]})

    assert payload["bikes"] == [
        {"motorbikeId": BIKE_A, "name": "Honda CB500F"},
        {"motorbikeId": BIKE_B, "name": "Suzuki GSR600"},
    ]
    fields = [row["field"] for row in payload["rows"]]
    assert fields == [to_camel(field) for field in COMPARISON_SPEC_FIELDS]
    # The camelCase spelling the client maps to a label, pinned explicitly.
    assert {"powerKw", "seatHeightMm", "a2Eligible", "priceBand"} <= set(fields)
    rows = {row["field"]: row["values"] for row in payload["rows"]}
    assert rows["category"] == ["naked", "naked"]
    assert rows["powerKw"] == [35.0, None]
    assert rows["a2Eligible"] == [True, None]
    assert rows["seatHeightMm"] == [None, None]
    assert all(len(values) == len(payload["bikes"]) for values in rows.values())


def test_spec_comparison_names_render_at_the_year_range_floor(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """`spec_comparison`'s pinned per-caller floor is `YEAR_RANGE` (D5) — the
    compared bikes always carry it, distinguishable or not, and the keys stay
    exactly the pinned two (`motorbikeId`, `name`).
    """
    catalogue.by_name = {
        "Honda CB500F 2019": _Motorbike(BIKE_A, "Honda CB500F 2019", MotorbikeStatus.APPROVED),
        "Honda CB650R 2021": _Motorbike(BIKE_B, "Honda CB650R 2021", MotorbikeStatus.APPROVED),
    }
    catalogue.specs = [
        VerifiedSpecs(
            motorbike_id=BIKE_A,
            name="ignored",
            values=dict.fromkeys(COMPARISON_SPEC_FIELDS),
            parts=_named_parts(BIKE_A, manufacturer="Honda", model_name="CB500F", year_from=2019),
        ),
        VerifiedSpecs(
            motorbike_id=BIKE_B,
            name="ignored",
            values=dict.fromkeys(COMPARISON_SPEC_FIELDS),
            parts=_named_parts(BIKE_B, manufacturer="Honda", model_name="CB650R", year_from=2021),
        ),
    ]

    payload = _execute(
        spec_comparison.NAME, ctx, {"names": ["Honda CB500F 2019", "Honda CB650R 2021"]}
    )

    assert payload["bikes"] == [
        {"motorbikeId": BIKE_A, "name": "Honda CB500F (from 2019)"},
        {"motorbikeId": BIKE_B, "name": "Honda CB650R (from 2021)"},
    ]
    for bike in payload["bikes"]:
        assert set(bike) == {"motorbikeId", "name"}


def test_spec_comparison_answers_unknown_bike_for_a_name_it_cannot_resolve(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """The shared resolution-failure result — and no half-built comparison."""
    catalogue.by_name = {
        "Honda CB500F": _Motorbike(BIKE_A, "Honda CB500F", MotorbikeStatus.APPROVED)
    }

    payload = _execute(spec_comparison.NAME, ctx, {"names": ["Honda CB500F", "Bikeley 999"]})

    assert payload == {"unknownBike": "Bikeley 999"}
    # Nothing was loaded: the call stops at the unresolvable reference.
    assert catalogue.requested_ids == []
    # It is a normal, recorded outcome, not a failure.
    assert ctx.collector.tool_calls[0]["status"] == "succeeded"


def test_spec_comparison_answers_unknown_bike_for_an_unapproved_id(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """An id is a reference like any other: unapproved entries are not showable."""
    catalogue.by_id = {
        BIKE_A: _Motorbike(BIKE_A, "Honda CB500F", MotorbikeStatus.APPROVED),
        BIKE_B: _Motorbike(BIKE_B, "Backlog Bike", MotorbikeStatus.BACKLOG),
    }

    payload = _execute(spec_comparison.NAME, ctx, {"motorbikeIds": [BIKE_A, BIKE_B]})

    assert payload == {"unknownBike": BIKE_B}


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"names": ["Honda CB500F"]},
        {"names": ["A", "B", "C"], "motorbikeIds": [BIKE_A, BIKE_B]},
    ],
    ids=["nothing", "one-bike", "five-bikes"],
)
def test_spec_comparison_rejects_a_call_that_cannot_be_a_comparison(
    ctx: tools.ToolContext, catalogue: Any, arguments: dict[str, Any]
) -> None:
    """Args-schema validation: fewer than two or more than four bikes.

    The call never runs, so it is not recorded — a rejected argument list is not
    an executed tool call.
    """
    with pytest.raises(ValidationError):
        _execute(spec_comparison.NAME, ctx, arguments)

    assert ctx.collector.tool_calls == []
    assert catalogue.requested_ids == []


# --- licence_fit_check --------------------------------------------------------


def _approved(catalogue: Any, name: str = "Honda CB500F", **values: Any) -> None:
    """Put one approved model with the given verified specs in the stubbed catalogue."""
    catalogue.by_name[name] = _Motorbike(BIKE_A, name, MotorbikeStatus.APPROVED)
    catalogue.by_id[BIKE_A] = catalogue.by_name[name]
    catalogue.specs = [_specs(BIKE_A, name, **values)]


def test_licence_fit_check_returns_the_frozen_rule_shape(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """The pinned result: the bike, then one rule object per check.

    The verdicts and the evidence strings belong to `fit_check_service` (tested
    there); what this asserts is the shape the chat UI's renderer reads and the
    fact that the evidence carries the verified figures at all.
    """
    _approved(catalogue, power_kw=35.0, wet_weight_kg=189.0, seat_height_mm=789)

    payload = _execute(
        licence_fit_check.NAME,
        ctx,
        {"motorbikeName": "Honda CB500F", "licence": "A2", "riderHeightCm": 165},
    )

    assert set(payload) == {"motorbikeId", "name", "rules"}
    assert payload["motorbikeId"] == BIKE_A
    assert payload["name"] == "Honda CB500F"
    for rule in payload["rules"]:
        assert set(rule) == {"rule", "label", "verdict", "evidence"}
        assert rule["verdict"] in {"pass", "fail", "unknown"}
        assert rule["label"]
    rules = {rule["rule"]: rule for rule in payload["rules"]}
    assert rules["a2_power"]["verdict"] == "pass"
    # The numbers used are in the evidence, not only in the verdict.
    assert "35.0 kW" in rules["a2_power"]["evidence"]
    assert "189 kg" in rules["a2_power_to_weight"]["evidence"]
    assert "789 mm" in rules["seat_height_fit"]["evidence"]


def test_licence_fit_check_records_a_read_path_valid_entry(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """What is persisted must survive `GET /api/chat-messages`' validation.

    The read path validates every stored `tool_calls[]` entry against the frozen
    `ToolCall` model, where a missing key is a 500 rather than a silent gap — so
    the recorded entry is validated here, at the only place that produces it.
    """
    _approved(catalogue, power_kw=35.0, wet_weight_kg=189.0, seat_height_mm=789)

    _execute(licence_fit_check.NAME, ctx, {"motorbikeName": "Honda CB500F", "insideLegMm": 780})

    (entry,) = ctx.collector.tool_calls
    validated = ToolCall.model_validate(entry)
    assert validated.tool == licence_fit_check.NAME
    assert validated.status.value == "succeeded"
    assert validated.result == entry["result"]
    # Arguments are recorded camelCase, defaults included, as the shape pins them.
    assert entry["arguments"] == {
        "motorbikeId": None,
        "motorbikeName": "Honda CB500F",
        "licence": "A2",
        "riderHeightCm": None,
        "insideLegMm": 780,
        "experience": None,
    }


def test_licence_fit_check_name_renders_at_the_year_range_floor(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """`licence_fit_check`'s pinned per-caller floor is `YEAR_RANGE` (D5), and
    the result's other pinned keys survive unchanged.
    """
    catalogue.by_name["Honda CB500F"] = _Motorbike(BIKE_A, "Honda CB500F", MotorbikeStatus.APPROVED)
    catalogue.by_id[BIKE_A] = catalogue.by_name["Honda CB500F"]
    catalogue.specs = [
        VerifiedSpecs(
            motorbike_id=BIKE_A,
            name="ignored",
            values=dict.fromkeys(COMPARISON_SPEC_FIELDS),
            parts=_named_parts(BIKE_A, manufacturer="Honda", model_name="CB500F", year_from=2019),
        )
    ]

    payload = _execute(licence_fit_check.NAME, ctx, {"motorbikeName": "Honda CB500F"})

    assert set(payload) == {"motorbikeId", "name", "rules"}
    assert payload["name"] == "Honda CB500F (from 2019)"


def test_licence_fit_check_answers_unknown_bike_for_a_name_it_cannot_resolve(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """The shared resolution failure, and no rules invented around it."""
    payload = _execute(licence_fit_check.NAME, ctx, {"motorbikeName": "Bikeley 999"})

    assert payload == {"unknownBike": "Bikeley 999"}
    assert ctx.collector.tool_calls[0]["status"] == "succeeded"


@pytest.mark.parametrize(
    "arguments",
    [
        {"licence": "A2"},
        {"motorbikeName": "Honda CB500F", "riderHeightCm": 17},
        {"motorbikeName": "Honda CB500F", "insideLegMm": 78},
        {"motorbikeName": "Honda CB500F", "licence": "A1"},
    ],
    ids=["no-bike", "metres-for-centimetres", "centimetres-for-millimetres", "unsupported-licence"],
)
def test_licence_fit_check_rejects_arguments_it_cannot_answer_honestly(
    ctx: tools.ToolContext, catalogue: Any, arguments: dict[str, Any]
) -> None:
    """A unit slip or an unsupported licence must fail loudly, not produce a verdict."""
    with pytest.raises(ValidationError):
        _execute(licence_fit_check.NAME, ctx, arguments)

    assert ctx.collector.tool_calls == []


# --- cost_estimator -----------------------------------------------------------


def test_cost_estimator_returns_the_frozen_estimate_shape(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """The pinned estimate: EUR line items, their total, assumptions, table version."""
    _approved(catalogue, category="naked", engine_cc=471, power_kw=35.0, price_band="mid")

    payload = _execute(
        cost_estimator.NAME, ctx, {"motorbikeName": "Honda CB500F", "annualKm": 8000}
    )

    assert set(payload) == {
        "motorbikeId",
        "name",
        "currency",
        "lineItems",
        "total",
        "assumptions",
        "coefficientsVersion",
    }
    assert payload["currency"] == "EUR"
    assert payload["coefficientsVersion"] == cost_data.COEFFICIENTS_VERSION
    assert payload["lineItems"]
    for line in payload["lineItems"]:
        assert set(line) == {"label", "amount"}
        assert isinstance(line["amount"], int)
    assert payload["total"] == sum(line["amount"] for line in payload["lineItems"])
    # The estimate has to say what it rests on — this is the field that makes it
    # an estimate rather than a price.
    assert payload["assumptions"]
    assert ToolCall.model_validate(ctx.collector.tool_calls[0]).result == payload


def test_cost_estimator_is_deterministic_through_the_tool(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """Same bike, same mileage, same euros — twice in one conversation."""
    _approved(catalogue, category="naked", engine_cc=471, power_kw=35.0, price_band="mid")
    arguments = {"motorbikeName": "Honda CB500F", "annualKm": 11000}

    assert _execute(cost_estimator.NAME, ctx, arguments) == _execute(
        cost_estimator.NAME, ctx, arguments
    )


def test_cost_estimator_name_renders_at_the_year_range_floor(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """`cost_estimator`'s pinned per-caller floor is `YEAR_RANGE` (D5), and the
    other pinned result keys survive unchanged.
    """
    catalogue.by_name["Honda CB500F"] = _Motorbike(BIKE_A, "Honda CB500F", MotorbikeStatus.APPROVED)
    catalogue.by_id[BIKE_A] = catalogue.by_name["Honda CB500F"]
    catalogue.specs = [
        VerifiedSpecs(
            motorbike_id=BIKE_A,
            name="ignored",
            values=dict.fromkeys(COMPARISON_SPEC_FIELDS),
            parts=_named_parts(BIKE_A, manufacturer="Honda", model_name="CB500F", year_from=2019),
        )
    ]

    payload = _execute(cost_estimator.NAME, ctx, {"motorbikeName": "Honda CB500F"})

    assert set(payload) == {
        "motorbikeId",
        "name",
        "currency",
        "lineItems",
        "total",
        "assumptions",
        "coefficientsVersion",
    }
    assert payload["name"] == "Honda CB500F (from 2019)"


def test_cost_estimator_answers_unknown_bike_for_an_unapproved_id(
    ctx: tools.ToolContext, catalogue: Any
) -> None:
    """An id is a reference like any other: an unreviewed entry has no price to quote."""
    catalogue.by_id = {BIKE_B: _Motorbike(BIKE_B, "Backlog Bike", MotorbikeStatus.BACKLOG)}

    payload = _execute(cost_estimator.NAME, ctx, {"motorbikeId": BIKE_B})

    assert payload == {"unknownBike": BIKE_B}


@pytest.mark.parametrize(
    "arguments",
    [{}, {"motorbikeName": "Honda CB500F", "annualKm": -1}, {"annualKm": 8000}],
    ids=["nothing", "negative-mileage", "no-bike"],
)
def test_cost_estimator_rejects_a_call_it_cannot_cost(
    ctx: tools.ToolContext, catalogue: Any, arguments: dict[str, Any]
) -> None:
    """No bike named, or a mileage that is not a mileage: nothing runs, nothing is recorded."""
    with pytest.raises(ValidationError):
        _execute(cost_estimator.NAME, ctx, arguments)

    assert ctx.collector.tool_calls == []


# --- retrieve_bike_knowledge (step 6.14: fencing sourceTitle and headingPath) --


def _chunk(
    *,
    source_title: str = "Document doc-1",
    heading_path: str | None = "Honda CB500F > Verdict",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="chunk-1",
        motorbike_id=BIKE_A,
        text="Plain prose.",
        score=0.9,
        source_document_id="doc-1",
        source_url="https://example.test/doc-1",
        source_title=source_title,
        heading_path=heading_path,
        page_number=None,
        sequence=1,
    )


def _result(*chunks: RetrievedChunk) -> retrieve_bike_knowledge.RetrieveBikeKnowledgeResult:
    return retrieve_bike_knowledge.RetrieveBikeKnowledgeResult(
        queries=["q"],
        applied_filters={},
        candidate_motorbike_ids=[BIKE_A],
        snippets=[retrieve_bike_knowledge._snippet(chunk) for chunk in chunks],
    )


@pytest.fixture
def rag(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Stub `rag_pipeline_service.retrieve` to return one scripted `RagResult`."""

    class _Recorder:
        def __init__(self) -> None:
            self.result: RagResult = RagResult(
                queries=["q"], applied_filters={}, candidate_motorbike_ids=[], chunks=[]
            )

    recorder = _Recorder()

    async def retrieve(session: Any, utterance: str, **kwargs: Any) -> RagResult:
        return recorder.result

    monkeypatch.setattr(rag_pipeline_service, "retrieve", retrieve)
    return recorder


def test_model_view_fences_text_source_title_and_heading_path(ctx: tools.ToolContext) -> None:
    """Every attacker-controlled field gets exactly one sentinel pair (D7)."""
    result = _result(_chunk())

    view = retrieve_bike_knowledge._model_view(result)

    (snippet,) = view["snippets"]
    for field in ("text", "sourceTitle", "headingPath"):
        assert snippet[field].startswith(retrieve_bike_knowledge.FENCE_START)
        assert snippet[field].endswith(retrieve_bike_knowledge.FENCE_END)
        assert snippet[field].count(retrieve_bike_knowledge.FENCE_START) == 1
        assert snippet[field].count(retrieve_bike_knowledge.FENCE_END) == 1


def test_model_view_truncates_title_and_heading_path_before_fencing(
    ctx: tools.ToolContext,
) -> None:
    """A title/trail longer than the cap is cut first, so a sentinel is never cut."""
    long_title = "T" * 500
    long_path = "P" * 500
    result = _result(_chunk(source_title=long_title, heading_path=long_path))

    view = retrieve_bike_knowledge._model_view(result)

    (snippet,) = view["snippets"]
    assert snippet["sourceTitle"] == retrieve_bike_knowledge._fenced_text(
        long_title[: retrieve_bike_knowledge.MODEL_VIEW_TITLE_CHARS]
    )
    assert snippet["headingPath"] == retrieve_bike_knowledge._fenced_text(
        long_path[: retrieve_bike_knowledge.MODEL_VIEW_HEADING_PATH_CHARS]
    )
    # The cap bites before fencing: the fenced string never contains the tail.
    assert "T" * retrieve_bike_knowledge.MODEL_VIEW_TITLE_CHARS + "T" not in snippet["sourceTitle"]


def test_model_view_never_fences_a_null_heading_path(ctx: tools.ToolContext) -> None:
    """`headingPath=None` (no ATX heading above the chunk) stays `None`, unfenced."""
    result = _result(_chunk(heading_path=None))

    view = retrieve_bike_knowledge._model_view(result)

    (snippet,) = view["snippets"]
    assert snippet["headingPath"] is None


def test_execute_records_the_plain_dump_while_the_model_view_is_fenced(
    ctx: tools.ToolContext, rag: Any
) -> None:
    """The 5.8 pin, still true after 6.14: recorded == plain `model_dump`, fences
    and caps appear only in the value handed to the model.
    """
    long_title = "T" * 500
    chunk = _chunk(source_title=long_title, heading_path="H" * 500)
    rag.result = RagResult(
        queries=["q"], applied_filters={}, candidate_motorbike_ids=[BIKE_A], chunks=[chunk]
    )

    payload = _execute(retrieve_bike_knowledge.NAME, ctx, {"query": "How is it regarded?"})

    (entry,) = ctx.collector.tool_calls
    snippet = retrieve_bike_knowledge._snippet(chunk)
    result = retrieve_bike_knowledge.RetrieveBikeKnowledgeResult(
        queries=["q"], applied_filters={}, candidate_motorbike_ids=[BIKE_A], snippets=[snippet]
    )
    plain = result.model_dump(by_alias=True)

    assert entry["result"] == plain
    assert entry["result"]["snippets"][0]["sourceTitle"] == long_title
    assert entry["result"]["snippets"][0]["text"] == chunk.text
    assert retrieve_bike_knowledge.FENCE_START not in json.dumps(entry["result"])

    # What the model actually received (the tool's JSON return, per `execute`).
    assert payload != plain
    (model_snippet,) = payload["snippets"]
    assert model_snippet["sourceTitle"] != long_title
    assert model_snippet["sourceTitle"].startswith(retrieve_bike_knowledge.FENCE_START)
    assert len(long_title) > retrieve_bike_knowledge.MODEL_VIEW_TITLE_CHARS
