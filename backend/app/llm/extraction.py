"""Specification extraction: the frozen spec column set as an LLM output schema.

This module is the project's first production LLM call. It holds three things
and nothing else:

* `ExtractedSpec` — a Pydantic model mirroring the **frozen** core
  specification column set 1:1 (`motorbike_spec.SPEC_FIELDS`), plus the handful
  of fields in `NON_SPEC_FIELDS` that belong to another table (the
  manufacturer). Every field is
  optional, because "the documents do not say" is the normal answer, and every
  field carries a validator that normalizes what a model may plausibly return
  (a foreign unit, a number as text, a category spelled differently) and clamps
  anything implausible to `None`. A junk value is never an error: the draft
  specification is admin-editable by design, and a null field the admin fills
  in is cheaper than a wrong field they have to notice first.
* `render_extraction_prompt` — the prompt assembly, including the fencing of
  document text as **untrusted data**.
* `build_extraction_chain` / `extract_spec` — the chain: the 2.16 factory plus
  `with_structured_output(..., method="json_schema")`, nothing else. The one
  provider concession lives on the schema itself, not in the chain: see
  `ExtractedSpec.model_json_schema`.

Which documents go in, in which order, and how much of them, is the caller's
decision (`app.services.spec_extraction_service`). Writing the result is the
caller's job too — this module never touches the database.
"""

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, StrEnum
from typing import Annotated, Any, cast

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from app.db.models.motorbike_spec import PRICE_BANDS, SPEC_CATEGORIES, SPEC_FIELDS
from app.llm.fencing import FENCE_END, FENCE_START, fence
from app.llm.models import get_chat_model
from app.llm.prompts import render_prompt

logger = logging.getLogger(__name__)

# The prompt file this module renders.
PROMPT_NAME = "spec_extraction"

# Fields of this schema that are **not** part of the frozen specification column
# set: they describe the motorbike, but they are stored elsewhere (the brand gets
# a `manufacturers` row of its own; the rest is the identity block on
# `motorbikes` itself — buildingline, model name, year range, type codes and
# variants, per `docs/roadmap/model-naming-data-model.md` §2.4/§2.5).
# `to_spec_values` iterates `SPEC_FIELDS`, so they are excluded from the spec
# write by construction — passing one of them to `upsert_draft_spec` would
# raise. `to_identity_values` is the counterpart for these fields.
NON_SPEC_FIELDS = (
    "manufacturer",
    "buildingline",
    "model_name",
    "year_from",
    "year_to",
    "type_codes",
    "variants",
)

# Plausibility window for a production year: wide enough to never reject a real
# motorcycle, narrow enough to catch a stray number (a price, a spec value) the
# model mistook for a year.
YEAR_MIN = 1900
YEAR_MAX = 2100

# The identity text fields' column widths (`motorbikes.buildingline` /
# `.model_name`), mirrored here so a long answer is truncated rather than
# rejected.
BUILDINGLINE_LENGTH = 64
MODEL_NAME_LENGTH = 128

# Defensive-only caps at the schema boundary. The *real* validation — shape,
# dedup, the ≤ 8 / ≤ 20 caps that actually matter — happens in
# `identity_validation.normalize_type_codes` / `normalize_variants`, called by
# `spec_extraction_service._assign_identity`. These are wider, just enough to
# keep a hallucinated long tail from becoming an unbounded payload before that
# real validation ever sees it.
MAX_RAW_TYPE_CODES = 16
MAX_RAW_VARIANTS = 30

# The pinned vocabularies as enums, so they reach the JSON schema the model is
# constrained by instead of living in prose only. Built from the single source
# of truth in the ORM model — they cannot drift from the columns.
ExtractedCategory = StrEnum(
    "ExtractedCategory", {value.upper(): value for value in SPEC_CATEGORIES}
)
ExtractedPriceBand = StrEnum("ExtractedPriceBand", {value.upper(): value for value in PRICE_BANDS})


@dataclass(frozen=True, slots=True)
class ExtractionDocument:
    """One source document as it is handed to the model."""

    title: str
    source_type: str
    markdown: str
    url: str | None = None


@dataclass(frozen=True, slots=True)
class _Quantity:
    """How one numeric field is normalized: units in, plausible range, rounding.

    `conversions` maps a unit as it appears right after the number onto the
    factor that turns it into the field's own unit; the first match wins, so
    the more specific pattern comes first. A number without a recognizable unit
    is taken to be in the field's unit already (that is what the prompt asks
    for). `decimals=None` means the column is an integer one.
    """

    conversions: tuple[tuple[re.Pattern[str], float], ...]
    minimum: float
    maximum: float
    decimals: int | None = None


def _units(*patterns: tuple[str, float]) -> tuple[tuple[re.Pattern[str], float], ...]:
    """Compile a unit table, keeping the given order (first match wins)."""
    return tuple((re.compile(pattern, re.IGNORECASE), factor) for pattern, factor in patterns)


# Plausibility windows are motorcycle-wide, not model-specific: they exist to
# catch a value that cannot be the field at all (a price in the seat height, a
# power figure that is really the torque), not to second-guess an unusual bike.
_QUANTITIES: dict[str, _Quantity] = {
    "engine_cc": _Quantity(
        conversions=_units(
            (r"\b(?:cu\.?\s?in|cubic\s?inch(?:es)?|ci)\b", 16.387064),
            (r"\b(?:l|lit(?:er|re)s?)\b", 1000.0),
            (r"\b(?:cc|ccm|cm3|cm³)\b", 1.0),
        ),
        minimum=25,
        maximum=3000,
    ),
    "cylinders": _Quantity(conversions=(), minimum=1, maximum=8),
    "power_kw": _Quantity(
        conversions=_units(
            (r"\bk\s?w\b", 1.0),
            # Mechanical horsepower vs. the metric PS/CV/pk Europe quotes.
            (r"\b(?:bhp|hp)\b", 0.745699872),
            (r"\b(?:ps|cv|pk)\b", 0.73549875),
        ),
        minimum=0.5,
        maximum=400,
        decimals=1,
    ),
    "torque_nm": _Quantity(
        conversions=_units(
            (r"\bn\s?m\b", 1.0),
            (r"\b(?:lbf?[\s.-]?ft|ft[\s.-]?lbf?)\b", 1.3558179),
            (r"\bkg[\s.-]?m\b", 9.80665),
        ),
        minimum=1,
        maximum=500,
        decimals=1,
    ),
    "wet_weight_kg": _Quantity(
        conversions=_units(
            (r"\bkg\b", 1.0),
            (r"\b(?:lbs?|pounds?)\b", 0.45359237),
        ),
        minimum=30,
        maximum=600,
        decimals=1,
    ),
    "seat_height_mm": _Quantity(
        conversions=_units(
            (r"\bmm\b", 1.0),
            (r"\bcm\b", 10.0),
            (r"(?:\b(?:in|inch(?:es)?)\b|\")", 25.4),
        ),
        minimum=400,
        maximum=1200,
    ),
    "tank_capacity_l": _Quantity(
        conversions=_units(
            (r"\bimp(?:erial)?\.?\s?gal(?:lons?)?\b", 4.54609),
            (r"\b(?:us\s?)?gal(?:lons?)?\b", 3.785411784),
            (r"\b(?:l|lit(?:er|re)s?)\b", 1.0),
        ),
        minimum=1,
        maximum=60,
        decimals=1,
    ),
    "top_speed_kmh": _Quantity(
        conversions=_units(
            (r"\b(?:km/?h|kph|kmh)\b", 1.0),
            (r"\bmph\b", 1.609344),
        ),
        minimum=30,
        maximum=500,
    ),
    "msrp_eur": _Quantity(
        conversions=_units((r"(?:€|\beur(?:os?)?\b)", 1.0)),
        minimum=100,
        maximum=1_000_000,
    ),
    # No unit to convert — a year is a year. Reusing the `_Quantity` machinery
    # buys the same text-parsing and plausibility-window handling every other
    # numeric field gets, for free.
    "year_from": _Quantity(conversions=(), minimum=YEAR_MIN, maximum=YEAR_MAX),
    "year_to": _Quantity(conversions=(), minimum=YEAR_MIN, maximum=YEAR_MAX),
}

# A price in another currency is not convertible here (no rate, no date), so it
# is dropped instead of stored as if it were euros. The prompt asks for EUR
# only and for the original to go into `extra`.
_FOREIGN_CURRENCY = re.compile(
    r"(?:[$£¥₹]|\b(?:usd|us\s?\$|gbp|chf|jpy|inr|pln|czk|sek|nok|dkk|cad|aud)\b)",
    re.IGNORECASE,
)

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
# A thousands separator ("1,234 mm") vs. a decimal comma ("12,5 kW").
_THOUSANDS_SEPARATOR = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")
# The same grouping written the continental way ("6.999 €"). Applied to prices
# only: for every other field a dot is a decimal point ("3.5 l"), and cents do
# not matter in a price band.
_THOUSANDS_DOT = re.compile(r"(?<=\d)\.(?=\d{3}(?!\d))")
# How much of the text after the number may name its unit.
_UNIT_WINDOW = 16

# Words a model uses for a yes/no specification when it does not answer with a
# boolean. Anything else (notably "optional") stays unknown: `abs = false`
# claims the bike cannot have it, which is a different statement.
_TRUE_WORDS = frozenset({"true", "yes", "y", "standard", "std", "series", "fitted", "1"})
_FALSE_WORDS = frozenset({"false", "no", "n", "none", "not available", "unavailable", "0"})

# Keeps a hallucinated long tail from becoming a JSONB blob.
MAX_MAPPING_ENTRIES = 20
MAX_MAPPING_KEY_CHARS = 64
MAX_MAPPING_VALUE_CHARS = 500

_NON_VOCABULARY_CHARACTERS = re.compile(r"[^a-z0-9]+")


def _to_text(value: Any) -> str | None:
    """Return `value` as trimmed text, or `None` when it carries no text."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _normalize_quantity(value: Any, quantity: _Quantity) -> Any:
    """Return `value` in the field's own unit, or `None` when it is unusable.

    Anything the parser cannot make sense of returns `None` rather than
    raising: the extraction schema clamps junk, it does not reject documents.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
    else:
        parsed = _parse_quantity_text(value, quantity)
        if parsed is None:
            return None
        number = parsed

    if not quantity.minimum <= number <= quantity.maximum:
        return None
    if quantity.decimals is None:
        return int(round(number))
    return round(number, quantity.decimals)


def _parse_quantity_text(value: Any, quantity: _Quantity) -> float | None:
    """Parse "98 hp" / "1,234 mm" / "€6.999" into the field's own unit."""
    text = _to_text(value)
    if text is None:
        return None
    if _is_price(quantity):
        if _FOREIGN_CURRENCY.search(text):
            return None
        text = _THOUSANDS_DOT.sub("", text)

    text = _THOUSANDS_SEPARATOR.sub("", text)
    text = _DECIMAL_COMMA.sub(".", text)
    match = _NUMBER.search(text)
    if match is None:
        return None

    number = float(match.group())
    # Only the unit adjacent to the number counts: "73.6 kW (100 hp)" is kW.
    unit = text[match.end() : match.end() + _UNIT_WINDOW].split("(")[0]
    for pattern, factor in quantity.conversions:
        if pattern.search(unit):
            return number * factor
    return number


def _is_price(quantity: _Quantity) -> bool:
    """Whether this field carries money (the only unit that is not converted)."""
    return quantity is _QUANTITIES["msrp_eur"]


def _quantity_validator(field: str) -> Callable[[Any], Any]:
    """Return the before-validator of one numeric field of the frozen set."""
    quantity = _QUANTITIES[field]

    def validate(value: Any) -> Any:
        return _normalize_quantity(value, quantity)

    return validate


def _normalize_flag(value: Any) -> Any:
    """Return a yes/no specification as a boolean, or `None` when unclear."""
    if isinstance(value, bool) or value is None:
        return value
    text = _to_text(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in _TRUE_WORDS:
        return True
    if lowered in _FALSE_WORDS:
        return False
    return None


def _vocabulary_validator(vocabulary: tuple[str, ...]) -> Callable[[Any], Any]:
    """Return a before-validator clamping to one pinned vocabulary, else `None`."""
    members = frozenset(vocabulary)

    def validate(value: Any) -> Any:
        text = _to_text(value)
        if text is None:
            return None
        candidate = _NON_VOCABULARY_CHARACTERS.sub("_", text.lower()).strip("_")
        return candidate if candidate in members else None

    return validate


def _discard(_value: Any) -> None:
    """Drop whatever the model returned for a field only the system may fill."""
    return None


def _normalize_mapping(value: Any) -> Any:
    """Return a JSONB mapping of trimmed text values, or `None` when empty."""
    if not isinstance(value, dict):
        return None

    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if len(normalized) >= MAX_MAPPING_ENTRIES:
            break
        key = _to_text(raw_key)
        # A non-text value (a number, a nested object) is kept as its text form:
        # the column is a free-form long tail, and dropping it loses provenance.
        text = None if raw_value is None else _to_text(str(raw_value))
        if key is None or text is None:
            continue
        normalized[key[:MAX_MAPPING_KEY_CHARS]] = text[:MAX_MAPPING_VALUE_CHARS]
    return normalized or None


def _capped_text_validator(max_length: int) -> Callable[[Any], Any]:
    """Return a before-validator: trimmed text, truncated to `max_length`."""

    def validate(value: Any) -> Any:
        text = _to_text(value)
        return None if text is None else text[:max_length]

    return validate


def _normalize_raw_type_codes(value: Any) -> list[str]:
    """Schema-level coercion only: trimmed strings, capped defensively.

    The real validation — shape, upper-casing, dedup, the ≤ 8 cap that
    actually matters — happens in `identity_validation.normalize_type_codes`,
    called by `spec_extraction_service._assign_identity`, so its `warnings`
    are not lost inside a Pydantic validator. A non-list or non-string entry
    is dropped rather than raising.
    """
    if not isinstance(value, list):
        return []
    codes: list[str] = []
    for entry in value:
        text = _to_text(entry)
        if text is None:
            continue
        codes.append(text)
        if len(codes) >= MAX_RAW_TYPE_CODES:
            break
    return codes


def _reshape_raw_specs_pairs(value: Any) -> dict[str, Any]:
    """Turn a variant's `specs` back into a flat mapping, accepting two shapes.

    The **wire** shape (what the provider actually returns — see
    `ExtractedSpec.model_json_schema`'s docstring) is an array of `{key,
    value}` pairs: `[{"key": "tank_capacity_l", "value": "30"}, ...]` →
    `{"tank_capacity_l": "30"}`. A JSON-schema object cannot carry both
    dynamically-named keys and full strict validation at the same time, so the
    provider is asked for pairs instead, and this puts them back into the
    shape `identity_validation.normalize_variants`'s `Variant` model actually
    expects. A plain mapping (a caller building an `ExtractedSpec` directly,
    as the tests do) is returned as-is. A malformed pair is dropped, never
    raised on; anything else becomes `{}`.
    """
    if isinstance(value, dict):
        return value
    if not isinstance(value, list):
        return {}
    specs: dict[str, str] = {}
    for pair in value:
        if not isinstance(pair, dict):
            continue
        key, val = pair.get("key"), pair.get("value")
        if isinstance(key, str) and isinstance(val, str):
            specs[key] = val
    return specs


def _cap_raw_variants(value: Any) -> list[dict[str, Any]]:
    """Schema-level coercion only: at most `MAX_RAW_VARIANTS` dict entries.

    Also reshapes each entry's `specs`, when present, through
    `_reshape_raw_specs_pairs` — into the flat mapping
    `identity_validation.normalize_variants` and `to_identity_values()` both
    deal in. An entry with no `specs` key is left exactly as it came in.

    The real validation — the `Variant` model, the ≤ 20 cap, the `specs` key
    whitelist — happens in `identity_validation.normalize_variants`, called by
    `spec_extraction_service._assign_identity`. A non-dict entry is dropped
    rather than raising (a `list[dict[str, Any]]` field would otherwise fail
    to validate on it).
    """
    if not isinstance(value, list):
        return []
    kept: list[dict[str, Any]] = []
    for entry in value[:MAX_RAW_VARIANTS]:
        if not isinstance(entry, dict):
            continue
        reshaped = dict(entry)
        if "specs" in reshaped:
            reshaped["specs"] = _reshape_raw_specs_pairs(reshaped["specs"])
        kept.append(reshaped)
    return kept


class ExtractedSpec(BaseModel):
    """What the model returns: the frozen specification column set, all optional.

    Field names are the column names, so `to_spec_values()` is exactly the
    full-object mapping `product_service.upsert_draft_spec` expects — the
    `NON_SPEC_FIELDS` are left out of it, because they are stored in another
    table. Unknown keys are ignored instead of rejected — a model that invents a
    field must not cost the run its whole specification.
    """

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Return the schema with every field named in `required`.

        OpenAI and Azure reject a `json_schema` response format whose `required`
        does not list *every* key in `properties` — even when `strict` is not
        passed ("'required' is required to be supplied and to be an array
        including every key in properties"). They expect optionality to be
        expressed as a `null` union instead, which every field of this schema
        already is, so listing all of them changes nothing about what the model
        may answer: a field it cannot fill comes back as `null`.

        What is *not* added, at the top level, is `additionalProperties: false`:
        the schema has to stay open for `extra` and `source_hints`, and —
        verified live through OpenRouter against both providers — a non-strict
        `json_schema` format is accepted without it. This is why the pinned
        method still carries the frozen field set.

        **A second provider concession, added in step 6.15 and discovered the
        same way** (three live OpenRouter calls, not a unit test): Pydantic's
        default schema for `variants: list[dict[str, Any]]` gives each array
        item `additionalProperties: true` — the literal boolean, not a schema
        — which OpenAI/Azure's `json_schema` validator rejects outright
        ("'additionalProperties' is required to be supplied and to be
        false"). Closing that object (`properties` + `"additionalProperties":
        False`) trades one rejection for another: every property in a closed
        object's `required` list must itself be a fully strict schema, and a
        dynamically-keyed `specs` mapping — the entire point of a spec
        *delta* — cannot be one, closed or open. There is no schema shape
        that lets one JSON object carry both fixed keys (`name`,
        `description`) *and* arbitrary ones (`specs`) under this provider's
        strict validation.

        The fix, a step further than `extra`/`source_hints`' plain open dict:
        `specs` goes over the wire as an **array of `{key, value}` pairs**
        instead of an object — a fully strict, statically-shaped schema with
        no dynamic keys anywhere — and `_reshape_raw_specs_pairs` (called from
        `_cap_raw_variants`, a `BeforeValidator` on the `variants` field) turns
        it back into a flat mapping before Pydantic ever sees it. So the fix
        stays confined to this file's two established provider-concession
        seams (this method for the *wire* schema, a `BeforeValidator` for the
        *parsed* shape): the field's Python type stays exactly
        `list[dict[str, Any]]`, `to_identity_values()`'s shape is unaffected,
        and `identity_validation.normalize_variants` (unchanged) still decides
        what is kept. See `docs/roadmap/stage-01/phase-6/shared-knowledge.md` — Step
        6.15's landed decisions record this as a disclosed deviation from the
        step's literal outline text.
        """
        schema = super().model_json_schema(*args, **kwargs)
        schema["required"] = list(schema["properties"])
        schema["properties"]["variants"]["items"] = {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
                "description": {"type": ["string", "null"]},
                "specs": {
                    "type": "array",
                    "description": "Spec-delta entries as {key, value} pairs, e.g. "
                    '{"key": "tank_capacity_l", "value": "30"}.',
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["key", "value"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["name", "description", "specs"],
            "additionalProperties": False,
        }
        return schema

    # Not a specification column: the brand becomes a `manufacturers` row, which
    # `spec_extraction_service` resolves after the draft specification is written.
    manufacturer: Annotated[str | None, BeforeValidator(_to_text)] = Field(
        default=None,
        description="Brand name only, without the model designation; null if unclear.",
    )
    # Not specification columns either: the identity block on `motorbikes`
    # itself (`buildingline`, `model_name`, `year_from`, `year_to`,
    # `type_codes`, `variants`). `spec_extraction_service._assign_identity`
    # merges these into the row per D2b and writes them through
    # `product_service.assign_identity`. Only schema-level coercion happens
    # here; the real shape/cap validation is `identity_validation`'s.
    buildingline: Annotated[
        str | None, BeforeValidator(_capped_text_validator(BUILDINGLINE_LENGTH))
    ] = Field(
        default=None,
        description="The model family this generation belongs to (e.g. GS, MT, CBR), if the "
        "documents name one; null otherwise. Never a table/alias lookup, just the family word.",
    )
    model_name: Annotated[
        str | None, BeforeValidator(_capped_text_validator(MODEL_NAME_LENGTH))
    ] = Field(
        default=None,
        description="The marketing model name without the brand, e.g. 'R 1300 GS', 'MT-07'.",
    )
    year_from: Annotated[int | None, BeforeValidator(_quantity_validator("year_from"))] = Field(
        default=None, description="First production year of this generation."
    )
    year_to: Annotated[int | None, BeforeValidator(_quantity_validator("year_to"))] = Field(
        default=None,
        description="Last production year of this generation; null while still built.",
    )
    type_codes: Annotated[list[str], BeforeValidator(_normalize_raw_type_codes)] = Field(
        default_factory=list,
        description="Every manufacturer type code the documents print for this generation "
        "(e.g. K50, SC82, RM33) — invent none.",
    )
    variants: Annotated[list[dict[str, Any]], BeforeValidator(_cap_raw_variants)] = Field(
        default_factory=list,
        description="Other trims of this generation, as spec deltas from the base trim above "
        "plus a short description — never the base itself, never a full spec set.",
    )
    category: Annotated[
        ExtractedCategory | None, BeforeValidator(_vocabulary_validator(SPEC_CATEGORIES))
    ] = Field(default=None, description="One of the pinned categories; null if none fits.")
    engine_cc: Annotated[int | None, BeforeValidator(_quantity_validator("engine_cc"))] = Field(
        default=None, description="Displacement in cm³."
    )
    cylinders: Annotated[int | None, BeforeValidator(_quantity_validator("cylinders"))] = Field(
        default=None, description="Number of cylinders."
    )
    power_kw: Annotated[float | None, BeforeValidator(_quantity_validator("power_kw"))] = Field(
        default=None, description="Maximum power in kW."
    )
    torque_nm: Annotated[float | None, BeforeValidator(_quantity_validator("torque_nm"))] = Field(
        default=None, description="Maximum torque in Nm."
    )
    wet_weight_kg: Annotated[
        float | None, BeforeValidator(_quantity_validator("wet_weight_kg"))
    ] = Field(default=None, description="Wet/kerb weight in kg, fluids included.")
    seat_height_mm: Annotated[
        int | None, BeforeValidator(_quantity_validator("seat_height_mm"))
    ] = Field(default=None, description="Seat height in mm.")
    tank_capacity_l: Annotated[
        float | None, BeforeValidator(_quantity_validator("tank_capacity_l"))
    ] = Field(default=None, description="Fuel tank capacity in litres.")
    top_speed_kmh: Annotated[int | None, BeforeValidator(_quantity_validator("top_speed_kmh"))] = (
        Field(default=None, description="Top speed in km/h.")
    )
    abs: Annotated[bool | None, BeforeValidator(_normalize_flag)] = Field(
        default=None, description="True when ABS is standard, null when only optional."
    )
    a2_eligible: Annotated[bool | None, BeforeValidator(_normalize_flag)] = Field(
        default=None,
        description="Only when a document states A2 licence eligibility explicitly.",
    )
    price_band: Annotated[
        ExtractedPriceBand | None, BeforeValidator(_vocabulary_validator(PRICE_BANDS))
    ] = Field(default=None, description="Price band derived from the EUR price.")
    msrp_eur: Annotated[int | None, BeforeValidator(_quantity_validator("msrp_eur"))] = Field(
        default=None, description="List price in EUR; null for any other currency."
    )
    extra: Annotated[dict[str, str] | None, BeforeValidator(_normalize_mapping)] = Field(
        default=None, description="Additional named specifications as flat text values."
    )
    source_hints: Annotated[dict[str, str] | None, BeforeValidator(_normalize_mapping)] = Field(
        default=None, description="Per-field note naming where the value came from."
    )
    # Part of the frozen column set, so it is part of this schema — but a model
    # cannot know when it ran, so anything it returns here is discarded and the
    # caller's timestamp is what `to_spec_values` writes.
    extracted_at: Annotated[datetime | None, BeforeValidator(_discard)] = Field(
        default=None, description="Always null: the system records the extraction time."
    )

    @model_validator(mode="after")
    def _drop_an_impossible_year_range(self) -> "ExtractedSpec":
        """An end year before the start year cannot be a range: drop the end.

        Each field already passed its own plausibility window individually;
        this catches the pair being internally inconsistent (a model reading
        two unrelated years off a page). `year_from` is kept — it is still a
        plausible single fact — only `year_to` is cleared.
        """
        year_from, year_to = self.year_from, self.year_to
        if year_from is not None and year_to is not None and year_to < year_from:
            self.year_to = None
        return self

    def to_spec_values(self, *, extracted_at: datetime) -> dict[str, Any]:
        """Return the full-object mapping for `product_service.upsert_draft_spec`.

        Only the frozen column set is mapped: `manufacturer` (and any other
        `NON_SPEC_FIELDS`) is deliberately absent, because `upsert_draft_spec`
        rejects a key outside `SPEC_FIELDS`.

        `extracted_at` is the caller's timestamp, never the model's: a model
        cannot know when it ran, and the column records the extraction, not a
        date it read somewhere.
        """
        values: dict[str, Any] = {}
        for field in SPEC_FIELDS:
            value = getattr(self, field)
            values[field] = value.value if isinstance(value, Enum) else value
        values["extra"] = self.extra or {}
        values["extracted_at"] = extracted_at
        return values

    def filled_fields(self) -> tuple[str, ...]:
        """Names of the frozen fields this extraction actually filled."""
        return tuple(field for field in SPEC_FIELDS if getattr(self, field) is not None)

    def to_identity_values(self) -> dict[str, Any]:
        """Return the identity kwargs of `product_service.assign_identity` minus
        the manufacturer (`spec_extraction_service` resolves that separately).

        Exactly the keys `buildingline, model_name, year_from, year_to,
        type_codes, variants`, as plain Python — no Enums, nothing else in
        this schema is part of the identity block. The caller
        (`spec_extraction_service._assign_identity`) still has to merge these
        against the row's current identity per D2b before writing them;
        this method only shapes the extracted side of that merge.
        """
        return {
            "buildingline": self.buildingline,
            "model_name": self.model_name,
            "year_from": self.year_from,
            "year_to": self.year_to,
            "type_codes": list(self.type_codes),
            "variants": [dict(variant) for variant in self.variants],
        }


def render_extraction_prompt(name: str, documents: Sequence[ExtractionDocument]) -> str:
    """Render the extraction prompt for `name` over the given documents.

    The documents are rendered in the order they are passed — the caller has
    already decided which comes first and how much of each is included.
    """
    return render_prompt(
        PROMPT_NAME,
        name=name,
        documents=[
            ExtractionDocument(
                title=document.title,
                source_type=document.source_type,
                markdown=fence(document.markdown),
                url=document.url,
            )
            for document in documents
        ],
        categories=SPEC_CATEGORIES,
        price_bands=PRICE_BANDS,
        fence_start=FENCE_START,
        fence_end=FENCE_END,
    )


def build_extraction_chain(model: str | None = None) -> Runnable[LanguageModelInput, ExtractedSpec]:
    """Return the extraction chain: OpenRouter chat model + JSON-schema output.

    Raises:
        MissingApiKeyError: `OPENROUTER_API_KEY` is not configured.
    """
    chain = get_chat_model(model).with_structured_output(ExtractedSpec, method="json_schema")
    return cast("Runnable[LanguageModelInput, ExtractedSpec]", chain)


async def extract_spec(
    name: str,
    documents: Sequence[ExtractionDocument],
    *,
    model: str | None = None,
) -> ExtractedSpec:
    """Extract one specification for `name` from `documents`.

    Raises:
        MissingApiKeyError: `OPENROUTER_API_KEY` is not configured.
        Exception: whatever the gateway or the parser raises — the caller
            decides how loud a failed extraction is (in ingestion: a warning).
    """
    prompt = render_extraction_prompt(name, documents)
    logger.info(
        "Extracting specifications for %r from %d document(s), %d prompt characters.",
        name,
        len(documents),
        len(prompt),
    )
    return await build_extraction_chain(model).ainvoke([HumanMessage(prompt)])
