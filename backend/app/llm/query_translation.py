"""Query translation: conversational language in, a retrieval plan out.

A rider does not talk in search terms. "I'm 1.65 m, just got my A2, mostly city
commuting" contains three different things: prose to search for, hard
constraints to filter on, and (sometimes) a bike named by the customer. Feeding
that sentence to a search engine verbatim retrieves the worst of all three.

This module is the translation pass that splits it, and it holds nothing else:

* `SpecFilters` — the **filterable** part of the frozen specification column
  set (`motorbike_spec.SPEC_FIELDS`) as an LLM output schema, in the pinned
  project units (mm, kg, kW, cm³, price band). Every field is optional, every
  field carries the same normalizing validators the extraction schema uses, and
  what the model cannot support stays `null` — a filter is a claim about the
  customer, and an invented one silently empties the shortlist.
  `app.services.catalogue_search_service` turns it into SQL. (Importing it
  still loads this module's LangChain imports — acceptable, since its only
  consumer is the agent loop, which needs LangChain anyway.)
* `TranslatedQuery` — the whole plan: 1–3 search queries, the filters, and the
  bike names the conversation mentioned.
* `render_translation_prompt` / `build_translation_chain` / `translate_query` —
  the prompt assembly and the chain: the 2.16 factory plus
  `with_structured_output(..., method="json_schema")`, exactly as
  `extraction.py`, at the pinned `TRANSLATION_TEMPERATURE`. The provider
  concession lives on the schemas themselves (see
  `TranslatedQuery.model_json_schema`).

The model is `get_chat_model()` (i.e. `CHAT_MODEL`): translation is a utility
structured-output task like extraction, not the advisor's conversation
(`ADVISOR_MODEL`). Which history and which preferences go in is the caller's
decision, and nothing here touches the database.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Annotated, Any, cast

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.db.models.motorbike import NAME_LENGTH as MOTORBIKE_NAME_LENGTH
from app.db.models.motorbike_spec import PRICE_BANDS, SPEC_CATEGORIES

# The frozen units have exactly one implementation, and it is the extraction
# schema's: importing its validators (rather than restating the conversion
# tables) is what keeps "72 kW" and "98 hp" meaning the same thing on the way
# in and on the way out.
from app.llm.extraction import _normalize_flag, _quantity_validator, _vocabulary_validator
from app.llm.fencing import FENCE_END, FENCE_START, fence
from app.llm.models import get_chat_model
from app.llm.prompts import render_prompt

logger = logging.getLogger(__name__)

# The prompt file this module renders.
PROMPT_NAME = "query_translation"

# How many rewrites one translation may contribute. Three is the retrieval
# budget: every query is a full hybrid search, and the fusion in step 3.9 stops
# gaining from a fourth near-duplicate.
MAX_SEARCH_QUERIES = 3
MAX_QUERY_CHARS = 200
# A bike name is matched against `motorbikes.name`, so a longer answer cannot be
# a name the catalogue could hold.
MAX_TARGET_NAMES = 5
MAX_NAME_CHARS = MOTORBIKE_NAME_LENGTH

# Translation is a deterministic extraction task, not a creative one: the same
# utterance must produce the same retrieval plan, because a sampled filter is an
# invented claim about the customer. A module constant rather than configuration —
# there is no environment in which a warmer translation is wanted.
TRANSLATION_TEMPERATURE = 0.0

# Which frozen specification columns a filter set can constrain, and which it
# deliberately ignores. Together they are exactly `SPEC_FIELDS` — the drift
# guard in `tests/llm/test_query_translation.py` asserts that, because a frozen
# column that gains a filterable meaning without a field here would never be
# filtered on and nobody would see an error.
FILTERABLE_SPEC_FIELDS: tuple[str, ...] = (
    "category",
    "engine_cc",
    "power_kw",
    "wet_weight_kg",
    "seat_height_mm",
    "a2_eligible",
    "price_band",
)
# Why each of these is not filterable: `cylinders`, `torque_nm`,
# `tank_capacity_l`, `top_speed_kmh` and `abs` are things a customer discusses
# in prose (the search queries), not thresholds they set; `msrp_eur` is filtered
# through `price_band` (a customer states a budget, not a list price); `extra`
# and `source_hints` are a free-form long tail; `extracted_at` is bookkeeping.
UNFILTERED_SPEC_FIELDS: tuple[str, ...] = (
    "cylinders",
    "torque_nm",
    "tank_capacity_l",
    "top_speed_kmh",
    "abs",
    "msrp_eur",
    "extra",
    "source_hints",
    "extracted_at",
)

# Every field of `SpecFilters` and the frozen column it constrains. The filter
# service reads the columns; the drift guard reads this mapping.
FILTER_FIELD_COLUMNS: dict[str, str] = {
    "categories": "category",
    "engine_cc_min": "engine_cc",
    "engine_cc_max": "engine_cc",
    "power_kw_min": "power_kw",
    "power_kw_max": "power_kw",
    "wet_weight_kg_max": "wet_weight_kg",
    "seat_height_mm_max": "seat_height_mm",
    "a2_eligible": "a2_eligible",
    "price_bands": "price_band",
}

# The pinned vocabularies as enums, so they reach the JSON schema the model is
# constrained by. Built from the single source of truth in the ORM model, like
# the extraction schema's — they cannot drift from the columns.
FilterCategory = StrEnum("FilterCategory", {value.upper(): value for value in SPEC_CATEGORIES})
FilterPriceBand = StrEnum("FilterPriceBand", {value.upper(): value for value in PRICE_BANDS})


@dataclass(frozen=True, slots=True)
class ActivePreference:
    """One active (non-superseded) preference as it is rendered into the prompt.

    A plain value object, not a `chat_preferences` row: this module stays free
    of the database, and the caller decides which preferences are relevant.
    """

    attribute: str
    value: str
    firmness: str


def _text_list_validator(
    *, maximum_items: int, maximum_chars: int
) -> Callable[[Any], list[str] | Any]:
    """Return a validator normalizing a list of short free-text answers.

    Trims, drops blanks, deduplicates case-insensitively (keeping the first
    spelling), truncates each entry and caps the list. A single string is
    accepted as a one-item list, because a model asked for a list occasionally
    answers with one value.
    """

    def validate(value: Any) -> list[str] | Any:
        if value is None:
            return []
        items = [value] if isinstance(value, str) else value
        if not isinstance(items, list | tuple):
            return []

        normalized: list[str] = []
        seen: set[str] = set()
        for item in items:
            if len(normalized) >= maximum_items:
                break
            if not isinstance(item, str):
                continue
            text = " ".join(item.split())[:maximum_chars].strip()
            if not text or text.casefold() in seen:
                continue
            seen.add(text.casefold())
            normalized.append(text)
        return normalized

    return validate


def _vocabulary_list_validator(vocabulary: tuple[str, ...]) -> Callable[[Any], list[str] | Any]:
    """Return a validator clamping a list to one pinned vocabulary.

    An entry outside the vocabulary is dropped, never an error: a category the
    model invented must not cost the whole translation. Same spelling tolerance
    as the extraction schema (`Sport Touring` → `sport_touring`).
    """
    normalize = _vocabulary_validator(vocabulary)

    def validate(value: Any) -> list[str] | Any:
        if value is None:
            return []
        items = [value] if isinstance(value, str) else value
        if not isinstance(items, list | tuple):
            return []

        normalized: list[str] = []
        for item in items:
            candidate = normalize(item)
            if candidate is not None and candidate not in normalized:
                normalized.append(candidate)
        return normalized

    return validate


def _require_every_property(schema: dict[str, Any], *, nested: bool = False) -> dict[str, Any]:
    """Name every property in `required`, in this schema and in every `$defs`.

    OpenAI and Azure reject a `json_schema` response format whose `required`
    does not list *every* key in `properties` — even without `strict` (the 2.17
    finding). Optionality is expressed as a `null` union instead, which every
    optional field of these schemas already is, so listing all of them changes
    nothing about what the model may answer. The nested `SpecFilters` object
    arrives as a `$defs` entry, and Pydantic does not call its
    `model_json_schema` while building the parent, so the walk has to do it.

    A **nested** object additionally has to carry `additionalProperties: false`
    (verified live through OpenRouter, 3.8: without it both OpenAI and Azure
    answer 400 `invalid_json_schema`, "In context=('properties',
    'spec_filters'), 'additionalProperties' is required to be supplied and to be
    false"). The 2.17 finding still holds for the **root** object, which
    therefore stays open exactly as the extraction schema's does; the nested one
    is closed because the provider gives no choice. `extra="ignore"` stays on
    both models regardless — the constraint is enforced provider-side, and a
    parser is the wrong place to learn that a model invented a key.
    """
    if "properties" in schema:
        schema["required"] = list(schema["properties"])
        if nested:
            schema["additionalProperties"] = False
    for definition in schema.get("$defs", {}).values():
        if isinstance(definition, dict):
            _require_every_property(definition, nested=True)
    return schema


class SpecFilters(BaseModel):
    """The filterable part of the frozen specification set, all optional.

    One field per bound, named after the column and the unit it carries, so
    neither the model nor a later reader has to remember which unit a number is
    in. `categories` and `price_bands` are lists because a rider legitimately
    accepts several ("naked or maybe a scrambler", "up to 8 000 €" → two
    bands); every other field is a single bound.

    Unknown keys are ignored rather than rejected — an invented filter must not
    cost the run its whole retrieval plan.
    """

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Return the schema with every field named in `required` (see above)."""
        return _require_every_property(super().model_json_schema(*args, **kwargs))

    categories: Annotated[
        list[FilterCategory], BeforeValidator(_vocabulary_list_validator(SPEC_CATEGORIES))
    ] = Field(
        default_factory=list,
        description="Motorcycle categories the customer asked for; empty when they named none.",
    )
    engine_cc_min: Annotated[int | None, BeforeValidator(_quantity_validator("engine_cc"))] = Field(
        default=None, description="Smallest acceptable displacement in cm³."
    )
    engine_cc_max: Annotated[int | None, BeforeValidator(_quantity_validator("engine_cc"))] = Field(
        default=None, description="Largest acceptable displacement in cm³."
    )
    power_kw_min: Annotated[float | None, BeforeValidator(_quantity_validator("power_kw"))] = Field(
        default=None, description="Smallest acceptable maximum power in kW."
    )
    power_kw_max: Annotated[float | None, BeforeValidator(_quantity_validator("power_kw"))] = Field(
        default=None, description="Largest acceptable maximum power in kW."
    )
    wet_weight_kg_max: Annotated[
        float | None, BeforeValidator(_quantity_validator("wet_weight_kg"))
    ] = Field(default=None, description="Heaviest acceptable wet/kerb weight in kg.")
    seat_height_mm_max: Annotated[
        int | None, BeforeValidator(_quantity_validator("seat_height_mm"))
    ] = Field(default=None, description="Highest acceptable seat height in mm.")
    a2_eligible: Annotated[bool | None, BeforeValidator(_normalize_flag)] = Field(
        default=None,
        description="True when the customer rides on an A2 (restricted) licence.",
    )
    price_bands: Annotated[
        list[FilterPriceBand], BeforeValidator(_vocabulary_list_validator(PRICE_BANDS))
    ] = Field(
        default_factory=list,
        description="Price bands the stated budget allows; empty when no budget was stated.",
    )

    def values(self) -> dict[str, Any]:
        """Return the filters as plain Python values, enum members unwrapped.

        The SQL layer binds strings, not enum members, and a caller logging or
        persisting a filter set wants the same plain shape.
        """
        plain: dict[str, Any] = {}
        for field in type(self).model_fields:
            value = getattr(self, field)
            if isinstance(value, list):
                plain[field] = [item.value if isinstance(item, Enum) else item for item in value]
            else:
                plain[field] = value.value if isinstance(value, Enum) else value
        return plain

    def is_empty(self) -> bool:
        """Whether nothing is constrained (the whole approved catalogue matches).

        `a2_eligible=False` is a constraint like any other, so emptiness is
        tested against `None` and the empty list — never against falsiness.
        """
        return all(
            value is None or (isinstance(value, list) and not value)
            for value in self.values().values()
        )


class TranslatedQuery(BaseModel):
    """What the translation returns: the retrieval plan for one turn."""

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Return the schema with every field named in `required` (see above)."""
        return _require_every_property(super().model_json_schema(*args, **kwargs))

    search_queries: Annotated[
        list[str],
        BeforeValidator(
            _text_list_validator(maximum_items=MAX_SEARCH_QUERIES, maximum_chars=MAX_QUERY_CHARS)
        ),
    ] = Field(
        default_factory=list,
        description=(
            f"One to {MAX_SEARCH_QUERIES} standalone search queries over motorcycle prose, "
            "each covering a different facet of the need."
        ),
    )
    spec_filters: SpecFilters = Field(
        default_factory=SpecFilters,
        description="The hard, checkable constraints the conversation supports.",
    )
    target_motorbike_names: Annotated[
        list[str],
        BeforeValidator(
            _text_list_validator(maximum_items=MAX_TARGET_NAMES, maximum_chars=MAX_NAME_CHARS)
        ),
    ] = Field(
        default_factory=list,
        description="Motorcycle models the conversation names, as they were written.",
    )


def render_translation_prompt(
    utterance: str,
    *,
    history_summary: str | None = None,
    preferences: Sequence[ActivePreference] = (),
) -> str:
    """Render the translation prompt for one customer utterance.

    Args:
        utterance: What the customer just wrote, verbatim. It is rendered as
            quoted data, fenced, and the prompt says so.
        history_summary: A short recap of the conversation so far, or `None` to
            omit the block entirely (the first turn has no history).
        preferences: The active preferences, in the caller's order. Omitted when
            empty.

    Every context block is stripped of anything resembling a fence marker
    (`fencing.fence`) before it is rendered inside one, the same pattern
    `extraction.render_extraction_prompt` uses for fetched documents.
    """
    return render_prompt(
        PROMPT_NAME,
        utterance=fence(utterance),
        history_summary=fence(history_summary) if history_summary else None,
        preferences=[
            ActivePreference(
                attribute=preference.attribute,
                value=fence(preference.value),
                firmness=preference.firmness,
            )
            for preference in preferences
        ],
        categories=SPEC_CATEGORIES,
        price_bands=PRICE_BANDS,
        max_search_queries=MAX_SEARCH_QUERIES,
        fence_start=FENCE_START,
        fence_end=FENCE_END,
    )


def build_translation_chain(
    model: str | None = None,
) -> Runnable[LanguageModelInput, TranslatedQuery]:
    """Return the translation chain: OpenRouter chat model + JSON-schema output.

    `temperature` rides along with the response format: `with_structured_output`
    binds its extra keyword arguments to the model, so the pinned
    `TRANSLATION_TEMPERATURE` reaches the request without a second wrapper and
    without touching the 2.17 structured-output mechanics.

    Raises:
        MissingApiKeyError: `OPENROUTER_API_KEY` is not configured.
    """
    chain = get_chat_model(model).with_structured_output(
        TranslatedQuery,
        method="json_schema",
        temperature=TRANSLATION_TEMPERATURE,
    )
    return cast("Runnable[LanguageModelInput, TranslatedQuery]", chain)


async def translate_query(
    utterance: str,
    *,
    history_summary: str | None = None,
    preferences: Sequence[ActivePreference] = (),
    model: str | None = None,
) -> TranslatedQuery:
    """Translate one customer utterance into a retrieval plan.

    Raises:
        MissingApiKeyError: `OPENROUTER_API_KEY` is not configured.
        Exception: whatever the gateway or the parser raises — the caller
            decides how loud a failed translation is.
    """
    prompt = render_translation_prompt(
        utterance, history_summary=history_summary, preferences=preferences
    )
    logger.info(
        "Translating a %d-character utterance with %d active preference(s).",
        len(utterance),
        len(preferences),
    )
    translated = await build_translation_chain(model).ainvoke([HumanMessage(prompt)])
    logger.info(
        "Translation returned %d query/queries, %d named bike(s); filters: %s.",
        len(translated.search_queries),
        len(translated.target_motorbike_names),
        "none" if translated.spec_filters.is_empty() else translated.spec_filters.values(),
    )
    return translated
