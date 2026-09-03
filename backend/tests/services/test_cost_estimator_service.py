"""`app/services/cost_estimator_service.py` + `cost_data.py` — the estimate's promises.

A cost estimate is the most authoritative-looking thing this advisor produces, so
the properties worth testing are the ones that keep it honest:

* **reproducible** — same bike, same mileage, same euros. No clock, no
  randomness, no pricing call;
* **every line rests on a verified specification** — a missing price, power or
  displacement removes the line it feeds and adds an assumption naming the gap,
  rather than substituting a plausible number;
* **the assumptions are never empty** and always end with the "not a quote"
  disclaimer plus the coefficient version, because that is what turns a number
  into an estimate;
* **the coefficient table covers the catalogue's vocabularies** — a new category
  or price band must not silently fall back to a neutral factor.

The one pinned arithmetic case doubles as the calibration record: a mid-band
471 cm³ naked at 8 000 km/year comes to €1 500 a year of running cost, which is
the real-world German range for that bike.

No database: the one service read is stubbed and the "session" is an inert marker.
"""

import asyncio
from typing import Any

import pytest

from app.db.models.motorbike_spec import PRICE_BANDS, SPEC_CATEGORIES
from app.services import catalogue_search_service, cost_data, cost_estimator_service
from app.services.catalogue_search_service import COMPARISON_SPEC_FIELDS, VerifiedSpecs
from app.services.cost_estimator_service import CostEstimate
from app.services.naming_service import NameParts

BIKE = "01J0BIKE0000000000000000AA"
NAME = "Honda CB500F"
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

# The calibration case: a mid-band 471 cm³ naked with 35 kW, ridden 8 000 km/year.
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


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Replace `get_verified_specs` with a scripted single-entry answer."""

    class _Recorder:
        def __init__(self) -> None:
            self.entries: list[VerifiedSpecs] = []

    recorder = _Recorder()

    async def get_verified_specs(session: Any, motorbike_ids: Any) -> list[VerifiedSpecs]:
        return list(recorder.entries)

    monkeypatch.setattr(catalogue_search_service, "get_verified_specs", get_verified_specs)
    return recorder


def _estimate(catalogue: Any, specs: dict[str, Any] | None = None, **kwargs: Any) -> CostEstimate:
    """Script one specification set and cost it."""
    catalogue.entries = [
        VerifiedSpecs(
            motorbike_id=BIKE,
            name=NAME,
            values={field: (specs or {}).get(field) for field in COMPARISON_SPEC_FIELDS},
            parts=_PARTS,
        )
    ]
    estimate = asyncio.run(cost_estimator_service.estimate(_Session(), BIKE, **kwargs))
    assert estimate is not None
    return estimate


def _lines(estimate: CostEstimate) -> dict[str, int]:
    """The estimate's line items as label → amount."""
    return {line.label: line.amount for line in estimate.line_items}


# --- the calibration case -----------------------------------------------------


def test_the_calibrated_commuter_estimate_is_exactly_this(catalogue: Any) -> None:
    """The pinned arithmetic of coefficient table 2026.1, line by line.

    Changing a coefficient must change this test — that is the point of a
    versioned table: the numbers a customer saw stay explainable.
    """
    estimate = _estimate(catalogue, COMMUTER, annual_km=8000)

    assert estimate.currency == "EUR"
    assert estimate.coefficients_version == cost_data.COEFFICIENTS_VERSION
    assert _lines(estimate) == {
        "Purchase price": 7500,
        "Registration & plates (one-off)": 120,
        "Riding gear (one-off)": 900,
        "Insurance /year": 460,
        "Vehicle tax /year": 35,
        "Fuel /year": 604,
        "Maintenance & tyres /year": 401,
    }
    assert estimate.total == 10020
    # The running-cost half is the figure the calibration was checked against
    # (real-world German range for this bike and mileage: €1 500–1 800).
    running = sum(amount for label, amount in _lines(estimate).items() if label.endswith("/year"))
    assert running == 1500


def test_the_total_is_always_the_sum_of_the_lines(catalogue: Any) -> None:
    """No hidden line, no rounding drift between the parts and the whole."""
    for specs in (COMMUTER, {"engine_cc": 999, "power_kw": 118.8, "price_band": "premium"}, {}):
        estimate = _estimate(catalogue, specs)
        assert estimate.total == sum(line.amount for line in estimate.line_items)


def test_the_same_input_produces_the_same_numbers(catalogue: Any) -> None:
    """Determinism, stated as a test: an estimate a customer can be shown twice."""
    first = _estimate(catalogue, COMMUTER, annual_km=12000)
    second = _estimate(catalogue, COMMUTER, annual_km=12000)

    assert _lines(first) == _lines(second)
    assert first.total == second.total
    assert first.assumptions == second.assumptions


def test_mileage_scales_fuel_and_maintenance_only(catalogue: Any) -> None:
    """The two usage-driven lines move with the kilometres; nothing else does."""
    low = _lines(_estimate(catalogue, COMMUTER, annual_km=4000))
    high = _lines(_estimate(catalogue, COMMUTER, annual_km=16000))

    assert high["Fuel /year"] > low["Fuel /year"]
    assert high["Maintenance & tyres /year"] > low["Maintenance & tyres /year"]
    assert high["Insurance /year"] == low["Insurance /year"]
    assert high["Purchase price"] == low["Purchase price"]


# --- verified inputs, or no line ----------------------------------------------


def test_a_verified_msrp_wins_over_the_price_band(catalogue: Any) -> None:
    """The model's own price beats the bucket, and the assumption says which was used."""
    estimate = _estimate(catalogue, {**COMMUTER, "msrp_eur": 6790})

    assert _lines(estimate)["Purchase price"] == 6790
    assert "verified MSRP of €6,790" in estimate.assumptions[0]


def test_an_unpriced_model_gets_no_purchase_line_and_says_why(catalogue: Any) -> None:
    """Not a guessed price, not a zero: a missing line and a stated reason."""
    estimate = _estimate(catalogue, {"category": "naked", "engine_cc": 471, "power_kw": 35.0})

    assert "Purchase price" not in _lines(estimate)
    assert (
        "The catalogue has no verified price for this model, so no purchase price is included."
        in estimate.assumptions
    )


def test_an_unverified_power_figure_removes_the_insurance_line(catalogue: Any) -> None:
    """The premium is derived from power; without power there is no premium to show."""
    estimate = _estimate(catalogue, {"engine_cc": 471, "price_band": "mid"})

    assert "Insurance /year" not in _lines(estimate)
    assert any("no insurance" in note for note in estimate.assumptions)


def test_an_unverified_displacement_removes_tax_fuel_and_maintenance(catalogue: Any) -> None:
    """All three derive from displacement, so all three go — and one note says so."""
    estimate = _estimate(catalogue, {"power_kw": 35.0, "category": "naked", "price_band": "mid"})

    assert set(_lines(estimate)) == {
        "Purchase price",
        "Registration & plates (one-off)",
        "Riding gear (one-off)",
        "Insurance /year",
    }
    assert any(
        "vehicle tax, fuel and maintenance are not included" in note
        for note in estimate.assumptions
    )


def test_an_unverified_category_uses_the_neutral_insurance_class_and_discloses_it(
    catalogue: Any,
) -> None:
    """A neutral factor is a documented default, not a guess at the model's class."""
    estimate = _estimate(catalogue, {"engine_cc": 471, "power_kw": 35.0, "price_band": "mid"})

    assert _lines(estimate)["Insurance /year"] == 460
    assert any("neutral insurance class" in note for note in estimate.assumptions)


def test_a_model_with_nothing_verified_still_estimates_the_rider_side(catalogue: Any) -> None:
    """Two rider-side one-offs need no specification — and every gap is named."""
    estimate = _estimate(catalogue)

    assert _lines(estimate) == {
        "Registration & plates (one-off)": 120,
        "Riding gear (one-off)": 900,
    }
    assert estimate.total == 1020
    assert len(estimate.assumptions) >= 4


# --- what makes it an estimate ------------------------------------------------


@pytest.mark.parametrize(
    "specs",
    [COMMUTER, {}, {"engine_cc": 999, "power_kw": 118.8, "category": "sport_touring"}],
    ids=["calibrated", "nothing-verified", "big-bike"],
)
def test_the_assumptions_are_never_empty_and_always_disclaim(
    catalogue: Any, specs: dict[str, Any]
) -> None:
    """The `assumptions` field is the mitigation for an authoritative-looking number."""
    estimate = _estimate(catalogue, specs)

    assert estimate.assumptions
    assert all(note.strip() for note in estimate.assumptions)
    assert estimate.assumptions[-1] == (
        f"An estimate from coefficient table {cost_data.COEFFICIENTS_VERSION} — not a quote, "
        "and not a dealer offer."
    )
    assert any("8,000 km a year" in note for note in estimate.assumptions)


def test_an_id_that_is_not_an_approved_entry_returns_none(catalogue: Any) -> None:
    """`None` is what the tool turns into the pinned `{"unknownBike": …}` result."""
    catalogue.entries = []

    assert asyncio.run(cost_estimator_service.estimate(_Session(), BIKE)) is None


# --- the coefficient table ----------------------------------------------------


def test_the_coefficient_table_covers_the_catalogue_vocabularies() -> None:
    """Drift guard: a new category or price band must force a decision here.

    Without it, a newly added category would quietly take the neutral insurance
    class and a new price band would quietly lose its purchase price.
    """
    assert set(cost_data.INSURANCE_CLASS_FACTOR) == set(SPEC_CATEGORIES)
    assert set(cost_data.PRICE_BAND_PRICE_EUR) == set(PRICE_BANDS)


def test_the_price_bands_are_ordered_like_the_bands_they_represent() -> None:
    """budget < mid < upper < premium — a band midpoint that inverts is a typo."""
    prices = [cost_data.PRICE_BAND_PRICE_EUR[band] for band in PRICE_BANDS]

    assert prices == sorted(prices)
