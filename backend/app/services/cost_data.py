"""The cost coefficients the ownership estimate is built from — one versioned table.

Every number a `cost_estimator` line item is derived from lives here, and
`COEFFICIENTS_VERSION` travels with the result: an estimate the customer saw in
March must stay explainable in October, and "which coefficients produced this?"
has to be answerable from the stored tool call alone. Bump the version whenever
any value below changes.

Three deliberate constraints:

* **A Python constant, not configuration.** These are curated domain numbers,
  reviewed as code and versioned with it — not a deployment knob. Moving them to
  `.env` would make the stored `coefficientsVersion` meaningless.
* **No external pricing API.** The project's promise is a transparent estimate
  from a table anyone can read, not a quote it cannot stand behind.
* **Germany, EUR, 2026.** The market these numbers describe. `currency` is
  `"EUR"` project-wide, and the tax rate is the German one; a second market
  would be a second table, not a fudge factor.

Sanity check behind the calibration (`2026.1`, Honda CB500F, 8 000 km/year):
insurance €460, vehicle tax €35, fuel €604, maintenance & tyres €401 —
€1 500/year of running cost, against a real-world German range of roughly
€1 500–1 800 for that bike and mileage.
"""

from decimal import Decimal

# Bump on every change to the values below; it is stored with each estimate.
COEFFICIENTS_VERSION = "2026.1"

# The project-wide monetary unit (shared-knowledge pins `currency: "EUR"`).
CURRENCY = "EUR"

# Default mileage when the conversation has not said one. 8 000 km/year is the
# typical German leisure-plus-commute figure and the one the assumptions state.
DEFAULT_ANNUAL_KM = 8000

# --- purchase basis -----------------------------------------------------------

# What a model in each verified price band is assumed to cost new: the midpoint
# of the band as `motorbike_spec` defines it (budget < 5 k€ · mid 5–10 k€ ·
# upper 10–15 k€ · premium > 15 k€; the open-ended top band gets a
# representative price rather than an infinity).
PRICE_BAND_PRICE_EUR: dict[str, int] = {
    "budget": 3500,
    "mid": 7500,
    "upper": 12500,
    "premium": 18000,
}

# Registration, plates and the first technical inspection.
REGISTRATION_EUR = 120

# A first full set of gear: helmet, jacket, gloves, boots. A rider cost rather
# than a bike cost, which is why the label says "one-off" and the assumptions
# say what it buys.
RIDING_GEAR_EUR = 900

# --- insurance ----------------------------------------------------------------

# Liability plus partial cover for a rider aged 30+ with no claims, as a linear
# function of engine power — the strongest single driver of a German premium.
INSURANCE_BASE_EUR = Decimal("180")
INSURANCE_EUR_PER_KW = Decimal("8")

# The insurance class, as a factor on the premium: sport bikes are the expensive
# end, scooters the cheap one. Covers exactly `SPEC_CATEGORIES` (drift-guarded in
# the tests, so a new category forces a decision here).
INSURANCE_CLASS_FACTOR: dict[str, Decimal] = {
    "naked": Decimal("1.00"),
    "sport": Decimal("1.35"),
    "sport_touring": Decimal("1.05"),
    "touring": Decimal("1.05"),
    "adventure": Decimal("1.05"),
    "cruiser": Decimal("0.95"),
    "classic": Decimal("0.90"),
    "scrambler": Decimal("0.95"),
    "enduro": Decimal("1.10"),
    "supermoto": Decimal("1.20"),
    "scooter": Decimal("0.75"),
}
# Used when the catalogue has no verified category: a neutral class, disclosed in
# the assumptions rather than silently guessed at a specific one.
NEUTRAL_INSURANCE_CLASS_FACTOR = Decimal("1.00")

# --- vehicle tax --------------------------------------------------------------

# German motorcycle tax: €1.84 per 25 cm³ or part thereof.
TAX_EUR_PER_STEP = Decimal("1.84")
TAX_CC_STEP = 25

# --- fuel ---------------------------------------------------------------------

# Consumption estimated from displacement: a base plus a linear term, calibrated
# against real-world figures (471 cm³ → 4.1 l/100 km, 700 cm³ → 5.0,
# 999 cm³ → 6.2).
FUEL_BASE_L_PER_100KM = Decimal("2.2")
FUEL_L_PER_100KM_PER_100CC = Decimal("0.40")
FUEL_PRICE_EUR_PER_L = Decimal("1.85")

# --- maintenance --------------------------------------------------------------

# Dealer servicing at manufacturer intervals plus tyres: a fixed share, a
# displacement term (bigger engines cost more per service) and a mileage term
# (tyres and consumables).
MAINTENANCE_BASE_EUR = Decimal("140")
MAINTENANCE_EUR_PER_100CC = Decimal("30")
MAINTENANCE_EUR_PER_1000KM = Decimal("15")
