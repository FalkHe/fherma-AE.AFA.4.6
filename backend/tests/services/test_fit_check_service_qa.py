"""QA independent verification of step 3.12's `fit_check_service` — A2 boundaries
and rider fit.

Fresh angle from the dev's `test_fit_check_service.py`: cross-checks the A2
verdicts against `product_service._resolve_a2_eligible` (the catalogue's own
derivation, the thing this tool must never drift from) across a grid of values
including both exact boundaries, and proves via AST — not a read-through — that
the module's A2 math carries no bare `35`/`0.2` literal outside the imported
`product_service` constants.

No database: the one service read is stubbed and the "session" is an inert
marker.
"""

import ast
import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.services import catalogue_search_service, fit_check_service, product_service
from app.services.catalogue_search_service import COMPARISON_SPEC_FIELDS, VerifiedSpecs
from app.services.fit_check_service import Licence, Verdict
from app.services.naming_service import NameParts

BIKE = "01J0QAFIT0000000000000AA"
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


class _Session:
    """Marker object: the one read is stubbed, so nothing is ever executed."""


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch) -> Any:
    class _Recorder:
        def __init__(self) -> None:
            self.entries: list[VerifiedSpecs] = []

    recorder = _Recorder()

    async def get_verified_specs(session: Any, motorbike_ids: Any) -> list[VerifiedSpecs]:
        return list(recorder.entries)

    monkeypatch.setattr(catalogue_search_service, "get_verified_specs", get_verified_specs)
    return recorder


def _rules(catalogue: Any, specs: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    catalogue.entries = [
        VerifiedSpecs(
            motorbike_id=BIKE,
            name=NAME,
            values={f: specs.get(f) for f in COMPARISON_SPEC_FIELDS},
            parts=_PARTS,
        )
    ]
    check = asyncio.run(fit_check_service.check(_Session(), BIKE, **kwargs))
    assert check is not None
    return {rule.rule: rule for rule in check.rules}


# --- criterion 2: A2 boundaries never drift from the catalogue's own derivation --


@pytest.mark.parametrize(
    ("power_kw", "wet_weight_kg"),
    [
        (35.0, 175.0),  # exactly the power ceiling, comfortably inside the ratio
        (35.0, 174.0),  # exactly the power ceiling, ratio just over 0.2
        (35.1, 200.0),  # a hair over the power ceiling
        (20.0, 100.0),  # comfortably inside both
        (30.0, 149.0),  # ratio just over 0.2, power well inside
        (30.0, 150.0),  # ratio exactly 0.2
    ],
    ids=[
        "power-exact-pass",
        "power-exact-ratio-fail",
        "power-just-over-fail",
        "well-inside-pass",
        "ratio-just-over-fail",
        "ratio-exact-pass",
    ],
)
def test_a2_verdict_never_disagrees_with_the_catalogues_own_derivation(
    catalogue: Any, power_kw: float, wet_weight_kg: float
) -> None:
    """`_resolve_a2_eligible` (2.1) is the ground truth this tool must track — a
    silent drift here would tell a customer the wrong thing is legal.
    """
    expected = product_service._resolve_a2_eligible(
        {"power_kw": power_kw, "wet_weight_kg": wet_weight_kg}
    )
    rules = _rules(catalogue, {"power_kw": power_kw, "wet_weight_kg": wet_weight_kg})

    derived_pass = (
        rules["a2_power"].verdict is Verdict.PASS
        and rules["a2_power_to_weight"].verdict is Verdict.PASS
    )
    assert derived_pass is bool(expected)


def test_no_bare_a2_magic_numbers_in_the_service_source() -> None:
    """AST proof that `35` and `0.2` exist nowhere in this module's code except
    through the imported `product_service` constants — a hardcoded fallback
    would silently survive a future limit change without failing any test that
    only checks behaviour at today's limits.
    """
    source = Path(fit_check_service.__file__).read_text()
    tree = ast.parse(source)
    offending = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
        and node.value in (35, 0.2)
    ]
    assert offending == []


def test_a1_is_not_an_accepted_licence_value() -> None:
    """Deliberate omission, pinned in shared-knowledge: A1 has no verified
    catalogue counterpart, so it must not silently validate as a licence.
    """
    with pytest.raises(ValueError):
        Licence("A1")


# --- criterion 3: rider fit ------------------------------------------------------


def test_seat_height_and_weight_unknowns_are_independently_gated(catalogue: Any) -> None:
    """A missing seat height must not blank out the weight rule, and vice versa."""
    rules = _rules(catalogue, {"wet_weight_kg": 190.0}, rider_height_cm=170, experience=None)

    assert rules["seat_height_fit"].verdict is Verdict.UNKNOWN
    assert "no verified seat height" in rules["seat_height_fit"].evidence
    assert rules["weight_fit"].verdict is Verdict.UNKNOWN
    assert "experience level was not given" in rules["weight_fit"].evidence


def test_estimated_inside_leg_is_named_estimated_in_the_evidence(catalogue: Any) -> None:
    rules = _rules(catalogue, {"seat_height_mm": 800}, rider_height_cm=180)

    assert rules["seat_height_fit"].verdict in {Verdict.PASS, Verdict.FAIL}
    assert "estimated" in rules["seat_height_fit"].evidence


def test_a_stated_inside_leg_never_says_estimated(catalogue: Any) -> None:
    rules = _rules(catalogue, {"seat_height_mm": 800}, inside_leg_mm=810)

    assert "estimated" not in rules["seat_height_fit"].evidence
