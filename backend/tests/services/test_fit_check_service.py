"""`app/services/fit_check_service.py` — the verdicts, and above all the boundaries.

Everything this service does is decide `pass`/`fail`/`unknown` and compose the
evidence, so that is what these tests pin:

* **the A2 boundaries are inclusive** — 35.0 kW exactly and a ratio of exactly
  0.20 kW/kg are legal, and a hair over is not. This is the arithmetic a customer
  would be given wrong legal advice by, and it is the same derivation the
  catalogue's `a2_eligible` column uses;
* **a missing verified specification yields `unknown` with the gap named**, never
  a substituted number — and the same for a rider figure the conversation has not
  stated;
* **the two conditional rules appear exactly when they add something**: the
  restricted-version note only for a model above the limit, the catalogue's
  eligibility flag only when the derivation could not be completed.

No database: the one service read is stubbed and the "session" is an inert marker.
"""

import asyncio
from typing import Any

import pytest

from app.services import catalogue_search_service, fit_check_service
from app.services.catalogue_search_service import COMPARISON_SPEC_FIELDS, VerifiedSpecs
from app.services.fit_check_service import FitRule, Licence, RiderExperience, Verdict
from app.services.naming_service import NameParts

BIKE = "01J0BIKE0000000000000000AA"
NAME = "Honda CB500F"
# `model_name is None` so `render_name` falls back to `query_name` verbatim
# (the load-bearing fallback, data-model doc §5 step 1) — this fixture is not
# about naming, so the parts carry no structured identity.
_PARTS = NameParts(
    motorbike_id=BIKE,
    manufacturer=None,
    buildingline=None,
    model_name=None,
    year_from=None,
    year_to=None,
    query_name=NAME,
)


class _Session:
    """Marker object: the one read is stubbed, so nothing is ever executed."""


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Replace `get_verified_specs` with a scripted single-entry answer."""

    class _Recorder:
        def __init__(self) -> None:
            self.entries: list[VerifiedSpecs] = []
            self.requested: list[list[str]] = []

    recorder = _Recorder()

    async def get_verified_specs(session: Any, motorbike_ids: Any) -> list[VerifiedSpecs]:
        recorder.requested.append(list(motorbike_ids))
        return list(recorder.entries)

    monkeypatch.setattr(catalogue_search_service, "get_verified_specs", get_verified_specs)
    return recorder


def _specs(**values: Any) -> VerifiedSpecs:
    """One verified-specs entry: every comparable field, unstated ones missing."""
    return VerifiedSpecs(
        motorbike_id=BIKE,
        name=NAME,
        values={field: values.get(field) for field in COMPARISON_SPEC_FIELDS},
        parts=_PARTS,
    )


def _rules(
    catalogue: Any, specs: dict[str, Any] | None = None, **kwargs: Any
) -> dict[str, FitRule]:
    """Script one specification set, run the check and return its rules by id."""
    catalogue.entries = [_specs(**(specs or {}))]
    check = asyncio.run(fit_check_service.check(_Session(), BIKE, **kwargs))
    assert check is not None
    assert check.motorbike_id == BIKE
    assert check.name == NAME
    return {rule.rule: rule for rule in check.rules}


# --- the A2 boundaries --------------------------------------------------------


def test_exactly_thirty_five_kilowatts_and_exactly_zero_point_two_pass(catalogue: Any) -> None:
    """The limits are ceilings, not exclusive bounds — 35.0 kW / 175 kg is legal."""
    rules = _rules(catalogue, {"power_kw": 35.0, "wet_weight_kg": 175.0})

    assert rules["a2_power"].verdict is Verdict.PASS
    assert rules["a2_power"].evidence == "Verified power 35.0 kW is within the A2 limit of 35 kW."
    assert rules["a2_power_to_weight"].verdict is Verdict.PASS
    assert rules["a2_power_to_weight"].evidence == (
        "35.0 kW / 175 kg = 0.200 kW/kg, within the A2 limit of 0.20 kW/kg."
    )


def test_a_hair_over_either_limit_fails(catalogue: Any) -> None:
    """35.1 kW is not 35 kW, and 0.201 kW/kg is not 0.20 kW/kg."""
    over_power = _rules(catalogue, {"power_kw": 35.1, "wet_weight_kg": 250.0})
    assert over_power["a2_power"].verdict is Verdict.FAIL
    assert over_power["a2_power"].evidence == (
        "Verified power 35.1 kW is above the A2 limit of 35 kW."
    )

    over_ratio = _rules(catalogue, {"power_kw": 35.0, "wet_weight_kg": 174.0})
    assert over_ratio["a2_power"].verdict is Verdict.PASS
    assert over_ratio["a2_power_to_weight"].verdict is Verdict.FAIL
    assert over_ratio["a2_power_to_weight"].evidence == (
        "35.0 kW / 174 kg = 0.201 kW/kg, above the A2 limit of 0.20 kW/kg."
    )


# --- unknown verdicts always carry their reason -------------------------------


def test_a_missing_power_figure_is_unknown_and_says_so(catalogue: Any) -> None:
    """No verified power ⇒ no verdict, and the evidence names the gap."""
    rules = _rules(catalogue, {"wet_weight_kg": 189.0})

    assert rules["a2_power"].verdict is Verdict.UNKNOWN
    assert rules["a2_power"].evidence == (
        "The catalogue has no verified power output for this model."
    )
    assert rules["a2_power_to_weight"].verdict is Verdict.UNKNOWN
    assert rules["a2_power_to_weight"].evidence == (
        "The wet weight of 189 kg is verified, but the power output is not, so the ratio "
        "cannot be checked."
    )


def test_a_missing_weight_leaves_the_power_verdict_standing(catalogue: Any) -> None:
    """Half the inputs is half the answer, not a guess at the other half."""
    rules = _rules(catalogue, {"power_kw": 71.5})

    assert rules["a2_power"].verdict is Verdict.FAIL
    assert rules["a2_power_to_weight"].verdict is Verdict.UNKNOWN
    assert rules["a2_power_to_weight"].evidence == (
        "The power output of 71.5 kW is verified, but the wet weight is not, so the ratio "
        "cannot be checked."
    )


def test_nothing_verified_yields_only_unknowns(catalogue: Any) -> None:
    """A model with no verified specs produces reasons, never numbers."""
    rules = _rules(catalogue, {}, experience=RiderExperience.BEGINNER)

    assert {rule.verdict for rule in rules.values()} == {Verdict.UNKNOWN}
    assert all(rule.evidence for rule in rules.values())
    assert rules["a2_power_to_weight"].evidence == (
        "The catalogue has no verified power output or wet weight for this model."
    )
    assert rules["a2_eligible"].evidence == (
        "The catalogue has no verified A2 eligibility for this model."
    )


# --- the two conditional rules ------------------------------------------------


def test_the_restricted_version_note_appears_only_above_the_limit(catalogue: Any) -> None:
    """A 35 kW bike needs no restriction; a 54 kW / 184 kg one could have one."""
    within = _rules(catalogue, {"power_kw": 35.0, "wet_weight_kg": 189.0})
    assert "a2_restricted_version" not in within

    restrictable = _rules(catalogue, {"power_kw": 54.0, "wet_weight_kg": 184.0})
    assert restrictable["a2_power"].verdict is Verdict.FAIL
    assert restrictable["a2_restricted_version"].verdict is Verdict.PASS
    assert "35 kW / 184 kg = 0.190 kW/kg" in restrictable["a2_restricted_version"].evidence


def test_a_restriction_from_more_than_double_the_power_is_not_permitted(catalogue: Any) -> None:
    """The EU doubling rule: 71.5 kW cannot legally become a 35 kW A2 machine."""
    rules = _rules(catalogue, {"power_kw": 71.5, "wet_weight_kg": 185.0})

    assert rules["a2_restricted_version"].verdict is Verdict.FAIL
    assert rules["a2_restricted_version"].evidence == (
        "An A2 restriction may only come from a version of at most 70 kW; this model makes 71.5 kW."
    )


def test_a_restricted_version_can_still_miss_the_ratio(catalogue: Any) -> None:
    """A light bike restricted to 35 kW is still too powerful for its weight."""
    rules = _rules(catalogue, {"power_kw": 40.0, "wet_weight_kg": 160.0})

    assert rules["a2_restricted_version"].verdict is Verdict.FAIL
    assert "35 kW / 160 kg = 0.219 kW/kg" in rules["a2_restricted_version"].evidence


def test_the_catalogue_flag_is_the_fallback_and_not_a_second_opinion(catalogue: Any) -> None:
    """Both numbers verified ⇒ the derivation speaks; one missing ⇒ the flag does."""
    derived = _rules(catalogue, {"power_kw": 35.0, "wet_weight_kg": 189.0, "a2_eligible": True})
    assert "a2_eligible" not in derived

    fallback = _rules(catalogue, {"power_kw": 35.0, "a2_eligible": True})
    assert fallback["a2_eligible"].verdict is Verdict.PASS
    assert fallback["a2_eligible"].evidence == "The catalogue records this model as A2 eligible."

    refused = _rules(catalogue, {"wet_weight_kg": 200.0, "a2_eligible": False})
    assert refused["a2_eligible"].verdict is Verdict.FAIL
    assert refused["a2_eligible"].evidence == (
        "The catalogue records this model as not A2 eligible."
    )


def test_the_unrestricted_licence_has_one_rule_and_no_limits(catalogue: Any) -> None:
    """Licence A: say the one true thing instead of checking A2 limits nobody asked about."""
    rules = _rules(catalogue, {"power_kw": 118.8}, licence=Licence.A)

    assert [rule for rule in rules if rule.startswith("a2")] == []
    assert rules["licence_unrestricted"].verdict is Verdict.PASS
    assert rules["licence_unrestricted"].evidence == (
        "A full A licence has no power or power-to-weight limit."
    )


# --- rider fit ----------------------------------------------------------------


def test_seat_height_against_a_stated_inside_leg(catalogue: Any) -> None:
    """The margin is the rule: 789 mm over a 780 mm leg reaches, over 700 mm does not."""
    reaches = _rules(catalogue, {"seat_height_mm": 789}, inside_leg_mm=780)
    assert reaches["seat_height_fit"].verdict is Verdict.PASS
    assert reaches["seat_height_fit"].evidence == (
        "789 mm seat height against a 780 mm inside leg (+9 mm): both feet should reach "
        "the ground once the suspension sags."
    )

    tiptoes = _rules(catalogue, {"seat_height_mm": 789}, inside_leg_mm=700)
    assert tiptoes["seat_height_fit"].verdict is Verdict.FAIL
    assert "+89 mm" in tiptoes["seat_height_fit"].evidence


def test_a_body_height_yields_a_disclosed_estimate(catalogue: Any) -> None:
    """Deriving an inside leg from height is a guess about the *rider*, and it says so."""
    rules = _rules(catalogue, {"seat_height_mm": 789}, rider_height_cm=165)

    assert rules["seat_height_fit"].verdict is Verdict.PASS
    assert rules["seat_height_fit"].evidence == (
        "789 mm seat height against an inside leg of about 775 mm estimated for a 165 cm "
        "rider (+14 mm): both feet should reach the ground once the suspension sags. "
        "Give the actual inside leg to firm it up."
    )


def test_a_stated_inside_leg_beats_the_estimate(catalogue: Any) -> None:
    """Given both, the measured figure decides and the evidence shows no estimate."""
    rules = _rules(catalogue, {"seat_height_mm": 789}, rider_height_cm=165, inside_leg_mm=700)

    assert rules["seat_height_fit"].verdict is Verdict.FAIL
    assert "estimated" not in rules["seat_height_fit"].evidence


def test_no_rider_measurement_is_unknown_with_the_seat_height_still_shown(catalogue: Any) -> None:
    """The advisor is meant to read this and ask, so the bike's number is in the reason."""
    rules = _rules(catalogue, {"seat_height_mm": 840})

    assert rules["seat_height_fit"].verdict is Verdict.UNKNOWN
    assert rules["seat_height_fit"].evidence == (
        "The seat is 840 mm, but no rider height or inside leg was given, so the reach "
        "cannot be judged."
    )


def test_an_unverified_seat_height_is_unknown_even_with_a_rider_figure(catalogue: Any) -> None:
    """A rider figure cannot rescue a specification the catalogue does not have."""
    rules = _rules(catalogue, {}, inside_leg_mm=780)

    assert rules["seat_height_fit"].verdict is Verdict.UNKNOWN
    assert rules["seat_height_fit"].evidence == (
        "The catalogue has no verified seat height for this model."
    )


@pytest.mark.parametrize(
    ("experience", "wet_weight_kg", "verdict"),
    [
        (RiderExperience.BEGINNER, 189.0, Verdict.PASS),
        (RiderExperience.BEGINNER, 247.0, Verdict.FAIL),
        (RiderExperience.RETURNING, 229.0, Verdict.PASS),
        (RiderExperience.RETURNING, 231.0, Verdict.FAIL),
        (RiderExperience.EXPERIENCED, 320.0, Verdict.PASS),
    ],
    ids=["first-bike-ok", "first-bike-heavy", "returning-ok", "returning-heavy", "experienced"],
)
def test_weight_against_experience(
    catalogue: Any, experience: RiderExperience, wet_weight_kg: float, verdict: Verdict
) -> None:
    """The bands, including the experienced rider this check does not limit."""
    rules = _rules(catalogue, {"wet_weight_kg": wet_weight_kg}, experience=experience)

    assert rules["weight_fit"].verdict is verdict
    assert f"{wet_weight_kg:.0f} kg wet" in rules["weight_fit"].evidence


def test_an_unstated_experience_level_is_unknown_not_a_default(catalogue: Any) -> None:
    """Assuming "beginner" would be a claim about the customer nobody made."""
    rules = _rules(catalogue, {"wet_weight_kg": 189.0})

    assert rules["weight_fit"].verdict is Verdict.UNKNOWN
    assert rules["weight_fit"].evidence == (
        "The bike weighs 189 kg wet, but the rider's experience level was not given."
    )


# --- the unknown-bike answer --------------------------------------------------


def test_an_id_that_is_not_an_approved_entry_returns_none(catalogue: Any) -> None:
    """`None` is what the tool turns into the pinned `{"unknownBike": …}` result."""
    catalogue.entries = []

    assert asyncio.run(fit_check_service.check(_Session(), BIKE)) is None
    assert catalogue.requested == [[BIKE]]
