"""Total cost of ownership for one catalogue model — a transparent estimate.

"What does it cost to run?" is the question that decides a purchase, and it is
the one an advisor is most tempted to answer with a confident-sounding number.
This service answers it the only way the project can defend: verified
specifications of an approved model in, the versioned coefficient table of
`cost_data` applied, and every choice it made written into `assumptions`. The
result labels itself an estimate, carries `coefficientsVersion`, and is
reproducible — the same bike and the same mileage always produce the same
numbers, because there is no randomness, no clock and no external pricing call
anywhere in it.

Two rules that shape the output:

* **A line item needs a verified input.** No purchase price is invented for a
  model whose price the catalogue never verified, and no insurance premium is
  derived from an unverified power figure: the line is *omitted* and the omission
  becomes an assumption line the customer can read. An estimate with a visible
  gap is honest; one with a filled-in guess is not.
* **The total is a first-year total** — purchase price plus the one-off items
  plus one year of running costs — and the assumptions say so, because a bare
  sum of mixed one-off and annual lines would otherwise be unreadable.

The costing itself is pure: `estimate` does one service read (the verified specs)
and then computes. Nothing is written, nothing is committed.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import catalogue_search_service, cost_data, naming_service
from app.services.cost_data import COEFFICIENTS_VERSION, CURRENCY, DEFAULT_ANNUAL_KM
from app.services.naming_service import NameLevel

# The line-item labels, verbatim as the chat UI renders them (server-composed
# English, the same i18n exemption as operation messages). "/year" versus
# "(one-off)" is the only thing telling the customer what a number means, so the
# suffixes are part of the label, not a separate field.
PURCHASE_LABEL = "Purchase price"
REGISTRATION_LABEL = "Registration & plates (one-off)"
GEAR_LABEL = "Riding gear (one-off)"
INSURANCE_LABEL = "Insurance /year"
TAX_LABEL = "Vehicle tax /year"
FUEL_LABEL = "Fuel /year"
MAINTENANCE_LABEL = "Maintenance & tyres /year"


@dataclass(frozen=True, slots=True)
class CostLine:
    """One line of the estimate: a rendered label and whole euros."""

    label: str
    amount: int


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """The estimate for one model, ready to be mapped into the pinned tool result."""

    motorbike_id: str
    name: str
    currency: str
    line_items: list[CostLine]
    total: int
    assumptions: list[str]
    coefficients_version: str


@dataclass(slots=True)
class _Parts:
    """Accumulator for the lines and the assumptions they rest on."""

    lines: list[CostLine] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def add(self, label: str, amount: Decimal | int) -> None:
        """Append one line item, rounded to whole euros."""
        self.lines.append(CostLine(label=label, amount=_euro(amount)))

    def note(self, text: str) -> None:
        """Append one assumption line."""
        self.assumptions.append(text)


async def estimate(
    session: AsyncSession,
    motorbike_id: str,
    *,
    annual_km: int = DEFAULT_ANNUAL_KM,
) -> CostEstimate | None:
    """Estimate the first-year cost of owning `motorbike_id`.

    Args:
        session: Session the one read runs on; nothing is written or committed.
        motorbike_id: Catalogue id of an **approved** entry.
        annual_km: Kilometres per year the fuel and maintenance terms scale with.
            The caller validates the range; the default is the one the
            assumptions state.

    Returns:
        The estimate, or `None` when the id is not an approved catalogue entry —
        callers turn that into the pinned `{"unknownBike": …}` tool result. A
        model with no verified specifications at all still returns an estimate:
        it holds the rider-side one-off items and an assumption line per omitted
        cost, which is the honest answer rather than an error.
    """
    specs = await catalogue_search_service.get_verified_specs(session, [motorbike_id])
    if not specs:
        return None

    entry = specs[0]
    parts = _Parts()
    _add_purchase(parts, entry.values)
    _add_one_offs(parts)
    _add_insurance(parts, entry.values)
    _add_usage(parts, entry.values, annual_km)
    _add_closing_notes(parts, annual_km)

    # `YEAR_RANGE` is the pinned floor for a customer-visible single-bike answer
    # (docs/roadmap/model-naming-data-model.md §5): no context set here, since
    # an estimate is always about exactly one model.
    name = naming_service.render_name(entry.parts, min_level=NameLevel.YEAR_RANGE)
    return CostEstimate(
        motorbike_id=entry.motorbike_id,
        name=name,
        currency=CURRENCY,
        line_items=parts.lines,
        total=sum(line.amount for line in parts.lines),
        assumptions=parts.assumptions,
        coefficients_version=COEFFICIENTS_VERSION,
    )


def _add_purchase(parts: _Parts, values: dict[str, Any]) -> None:
    """Add the purchase price from the verified MSRP, else from the price band.

    The MSRP wins when the catalogue has one: it is the model's own number, while
    a band is a bucket. Neither verified means no purchase line at all.
    """
    msrp = values["msrp_eur"]
    if msrp is not None:
        parts.add(PURCHASE_LABEL, int(msrp))
        parts.note(f"Purchase price is the catalogue's verified MSRP of €{int(msrp):,}.")
        return

    band = values["price_band"]
    band_price = cost_data.PRICE_BAND_PRICE_EUR.get(band) if band is not None else None
    if band_price is not None:
        parts.add(PURCHASE_LABEL, band_price)
        parts.note(
            f'Purchase price is the middle of the catalogue\'s "{band}" price band '
            f"(€{band_price:,}); this model has no verified MSRP."
        )
        return

    parts.note(
        "The catalogue has no verified price for this model, so no purchase price is included."
    )


def _add_one_offs(parts: _Parts) -> None:
    """Add the two rider-side one-off items, which need no verified spec."""
    parts.add(REGISTRATION_LABEL, cost_data.REGISTRATION_EUR)
    parts.add(GEAR_LABEL, cost_data.RIDING_GEAR_EUR)
    parts.note(
        "Riding gear is a first full set (helmet, jacket, gloves, boots) — leave it out if "
        "you are already equipped."
    )


def _add_insurance(parts: _Parts, values: dict[str, Any]) -> None:
    """Add the annual premium: power drives it, the category classes it."""
    power_kw = values["power_kw"]
    if power_kw is None:
        parts.note(
            "The catalogue has no verified power output for this model, so no insurance "
            "estimate is included."
        )
        return

    category = values["category"]
    factor = cost_data.INSURANCE_CLASS_FACTOR.get(category) if category is not None else None
    if factor is None:
        factor = cost_data.NEUTRAL_INSURANCE_CLASS_FACTOR
        parts.note(
            "The model's category is not verified, so the insurance estimate uses the "
            "neutral insurance class."
        )

    premium = (
        cost_data.INSURANCE_BASE_EUR + cost_data.INSURANCE_EUR_PER_KW * _decimal(power_kw)
    ) * factor
    parts.add(INSURANCE_LABEL, premium)
    parts.note(
        "Insurance is liability plus partial cover for a rider aged 30+ with no claims, "
        f"scaled by the model's {_kw(power_kw)} kW and its insurance class."
    )


def _add_usage(parts: _Parts, values: dict[str, Any], annual_km: int) -> None:
    """Add the three displacement-driven annual costs: tax, fuel, maintenance."""
    engine_cc = values["engine_cc"]
    if engine_cc is None:
        parts.note(
            "The catalogue has no verified displacement for this model, so vehicle tax, "
            "fuel and maintenance are not included."
        )
        return

    hundred_cc = _decimal(engine_cc) / Decimal("100")
    kilometres = _decimal(annual_km)

    tax_steps = -(-int(engine_cc) // cost_data.TAX_CC_STEP)  # ceiling division
    parts.add(TAX_LABEL, cost_data.TAX_EUR_PER_STEP * tax_steps)

    consumption = (
        cost_data.FUEL_BASE_L_PER_100KM + cost_data.FUEL_L_PER_100KM_PER_100CC * hundred_cc
    )
    parts.add(
        FUEL_LABEL, consumption * kilometres / Decimal("100") * cost_data.FUEL_PRICE_EUR_PER_L
    )

    parts.add(
        MAINTENANCE_LABEL,
        cost_data.MAINTENANCE_BASE_EUR
        + cost_data.MAINTENANCE_EUR_PER_100CC * hundred_cc
        + cost_data.MAINTENANCE_EUR_PER_1000KM * kilometres / Decimal("1000"),
    )

    parts.note(
        f"Fuel use is estimated at {consumption:.1f} l/100 km from {int(engine_cc)} cm³ "
        f"at €{cost_data.FUEL_PRICE_EUR_PER_L} per litre; German vehicle tax is "
        f"€{cost_data.TAX_EUR_PER_STEP} per {cost_data.TAX_CC_STEP} cm³."
    )
    parts.note("Maintenance is dealer servicing at manufacturer intervals, tyres included.")


def _add_closing_notes(parts: _Parts, annual_km: int) -> None:
    """Add the two notes that apply to every estimate: what the total is, and what it is not."""
    parts.note(
        f"{annual_km:,} km a year in Germany; the total is the purchase price and the "
        "one-off items plus one year of running costs."
    )
    parts.note(
        f"An estimate from coefficient table {COEFFICIENTS_VERSION} — not a quote, and "
        "not a dealer offer."
    )


def _euro(amount: Decimal | int) -> int:
    """Round one amount to whole euros, half up — cents are noise in an estimate."""
    return int(_decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _decimal(value: Any) -> Decimal:
    """Convert a specification value to `Decimal` without float noise.

    `get_verified_specs` unwraps `Numeric` columns to `float`, so the string
    round trip (the `product_service` precedent) is what keeps the arithmetic
    exact and the output reproducible.
    """
    return Decimal(str(value))


def _kw(power_kw: Any) -> str:
    """Render a power figure the way the catalogue stores it: one decimal."""
    return f"{_decimal(power_kw):.1f}"
