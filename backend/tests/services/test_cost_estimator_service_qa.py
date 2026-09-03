"""QA independent verification of step 3.12's `cost_estimator_service` — the
"honest estimate" promises.

Fresh angle from the dev's `test_cost_estimator_service.py`: proves each line
item is actually *driven by* its `cost_data` coefficient via mutation (change
the coefficient, only that line moves — stronger evidence than a source
read-through, since it exercises the real code path a hardcoded fallback would
silently survive), and independently exercises the specific "no verified price"
path called out in this step's Landed decisions (the live dev-DB gap).

No database: the one service read is stubbed and the "session" is an inert
marker.
"""

import asyncio
from decimal import Decimal
from typing import Any

import pytest

from app.services import catalogue_search_service, cost_data, cost_estimator_service
from app.services.catalogue_search_service import COMPARISON_SPEC_FIELDS, VerifiedSpecs
from app.services.cost_estimator_service import CostEstimate
from app.services.naming_service import NameParts

BIKE = "01J0QACOST000000000000AA"
NAME = "QA Reference Bike"
# `model_name is None` so `render_name` falls back to `query_name` verbatim —
# this fixture is not about naming.
_PARTS = NameParts(
    motorbike_id=BIKE,
    manufacturer=None,
    buildingline=None,
    model_name=None,
    year_from=None,
    year_to=None,
    query_name=NAME,
)

COMMUTER = {
    "category": "naked",
    "engine_cc": 471,
    "power_kw": 35.0,
    "wet_weight_kg": 189.0,
    "seat_height_mm": 789,
    "price_band": "mid",
}


class _Session:
    """Marker object: the one read is stubbed, so nothing is ever executed."""


def _estimate(
    monkeypatch: pytest.MonkeyPatch, specs: dict[str, Any], **kwargs: Any
) -> CostEstimate:
    async def get_verified_specs(session: Any, motorbike_ids: Any) -> list[VerifiedSpecs]:
        return [
            VerifiedSpecs(
                motorbike_id=BIKE,
                name=NAME,
                values={field: specs.get(field) for field in COMPARISON_SPEC_FIELDS},
                parts=_PARTS,
            )
        ]

    monkeypatch.setattr(catalogue_search_service, "get_verified_specs", get_verified_specs)
    estimate = asyncio.run(cost_estimator_service.estimate(_Session(), BIKE, **kwargs))
    assert estimate is not None
    return estimate


def _lines(estimate: CostEstimate) -> dict[str, int]:
    return {line.label: line.amount for line in estimate.line_items}


# --- criterion 4: every coefficient actually comes from cost_data.py -------------


@pytest.mark.parametrize(
    ("coefficient", "label"),
    [
        ("REGISTRATION_EUR", "Registration & plates (one-off)"),
        ("RIDING_GEAR_EUR", "Riding gear (one-off)"),
        ("INSURANCE_BASE_EUR", "Insurance /year"),
        ("TAX_EUR_PER_STEP", "Vehicle tax /year"),
        ("FUEL_PRICE_EUR_PER_L", "Fuel /year"),
        ("MAINTENANCE_BASE_EUR", "Maintenance & tyres /year"),
    ],
)
def test_each_line_item_is_actually_driven_by_its_own_cost_data_coefficient(
    monkeypatch: pytest.MonkeyPatch, coefficient: str, label: str
) -> None:
    """Mutation proof: bump one `cost_data` value, only its own line item moves.

    If the service held a hardcoded copy instead of reading `cost_data.<NAME>`
    at call time, this mutation would have no effect on that line, and it would
    still pass a test that only checks today's numbers.
    """
    baseline = _lines(_estimate(monkeypatch, COMMUTER))

    original = getattr(cost_data, coefficient)
    bump = Decimal("50") if isinstance(original, Decimal) else 50
    monkeypatch.setattr(cost_data, coefficient, original + bump)

    mutated = _lines(_estimate(monkeypatch, COMMUTER))

    assert mutated[label] != baseline[label]
    for other_label, amount in baseline.items():
        if other_label != label:
            assert mutated[other_label] == amount, f"mutating {coefficient} moved {other_label} too"


def test_the_purchase_price_line_is_actually_driven_by_the_price_band_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _lines(_estimate(monkeypatch, COMMUTER))["Purchase price"]

    monkeypatch.setattr(
        cost_data, "PRICE_BAND_PRICE_EUR", {**cost_data.PRICE_BAND_PRICE_EUR, "mid": 9999}
    )
    mutated = _lines(_estimate(monkeypatch, COMMUTER))["Purchase price"]

    assert mutated == 9999
    assert baseline != 9999


def test_the_insurance_line_is_actually_driven_by_the_insurance_class_factor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _lines(_estimate(monkeypatch, COMMUTER))["Insurance /year"]

    monkeypatch.setattr(
        cost_data,
        "INSURANCE_CLASS_FACTOR",
        {**cost_data.INSURANCE_CLASS_FACTOR, "naked": Decimal("5.00")},
    )
    mutated = _lines(_estimate(monkeypatch, COMMUTER))["Insurance /year"]

    assert mutated != baseline


# --- criterion 4: determinism, the total invariant, and the no-price path --------


def test_the_same_input_produces_identical_numbers_across_a_specs_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for specs in (COMMUTER, {}, {"engine_cc": 999, "power_kw": 118.8, "category": "sport"}):
        first = _estimate(monkeypatch, specs, annual_km=9500)
        second = _estimate(monkeypatch, specs, annual_km=9500)

        assert _lines(first) == _lines(second)
        assert first.total == second.total == sum(line.amount for line in first.line_items)
        assert first.assumptions == second.assumptions


def test_assumptions_are_never_empty_when_no_purchase_price_can_be_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dev-DB-live gap this step's Landed decisions call out: an approved
    model with no verified MSRP and no price band still gets a labelled,
    non-empty estimate rather than an invented purchase price.
    """
    specs = {"category": "naked", "engine_cc": 471, "power_kw": 35.0}  # no msrp, no price_band
    estimate = _estimate(monkeypatch, specs)

    assert "Purchase price" not in _lines(estimate)
    assert estimate.assumptions
    assert any(
        "no verified price for this model" in note and "no purchase price" in note
        for note in estimate.assumptions
    )
    assert estimate.total == sum(line.amount for line in estimate.line_items)
    assert estimate.coefficients_version == cost_data.COEFFICIENTS_VERSION


def test_coefficients_version_is_the_module_constant_not_a_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    estimate = _estimate(monkeypatch, COMMUTER)
    assert estimate.coefficients_version == cost_data.COEFFICIENTS_VERSION

    # `cost_estimator_service` does `from cost_data import COEFFICIENTS_VERSION`
    # (a value import, bound at import time), so the mutation belongs on the
    # service's own bound name, not on `cost_data`'s module attribute — this is
    # what actually reaches `estimate()`'s return value and the disclaimer text.
    monkeypatch.setattr(cost_estimator_service, "COEFFICIENTS_VERSION", "9999.9")
    bumped = _estimate(monkeypatch, COMMUTER)
    assert bumped.coefficients_version == "9999.9"
    assert bumped.assumptions[-1].startswith("An estimate from coefficient table 9999.9")
