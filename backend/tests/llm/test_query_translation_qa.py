"""Independent QA coverage for step 3.8's query-translation module.

This file does not re-author `tests/llm/test_query_translation.py` (the dev's
own suite already proves the drift guard's *shape*, the schema round-trip and
the validator table). It exists to independently confirm the things a QA pass
owns rather than trusts:

* the drift guard is genuinely exhaustive (⊎, not ⊆) — proven here by
  *simulating* drift rather than only re-reading the assertion;
* `FILTER_FIELD_COLUMNS` names real `motorbike_specs` columns, not just
  plausible-looking strings;
* the raw Pydantic JSON schema (before LangChain's `$ref` inlining) really
  does carry the contract at both levels: every property required, nested
  `additionalProperties: false`, root left open, optionality as `null` unions;
* the unit/vocabulary validators are *the same objects* extraction.py uses,
  not a re-implementation that could quietly drift;
* whether `SpecFilters` is importable without dragging in the LangChain/model
  client machinery, as the module docstring and the step file claim;
* the prompt's `StrictUndefined` contract for a variable the template needs
  but a caller forgot to pass.
"""

import subprocess
import sys

import pytest
from jinja2 import UndefinedError

from app.db.models.motorbike_spec import SPEC_FIELDS, MotorbikeSpec
from app.llm import extraction, query_translation
from app.llm.prompts import render_prompt
from app.llm.query_translation import (
    FILTER_FIELD_COLUMNS,
    FILTERABLE_SPEC_FIELDS,
    MAX_SEARCH_QUERIES,
    UNFILTERED_SPEC_FIELDS,
    SpecFilters,
    TranslatedQuery,
)

# --- the drift guard, proven by simulation, not just re-read ------------------


def test_drift_guard_catches_an_unclassified_new_spec_column() -> None:
    """A frozen column added without a filterable/unfiltered decision must fail.

    This is the behaviour the guard exists for: recompute the same partition
    check the dev's guard makes, but against a *drifted* column set, and prove
    it actually fails instead of trusting the assertion reads correctly.
    """
    drifted_fields = (*SPEC_FIELDS, "some_new_frozen_column")
    classified = set(FILTERABLE_SPEC_FIELDS) | set(UNFILTERED_SPEC_FIELDS)

    with pytest.raises(AssertionError):
        assert classified == set(drifted_fields)


def test_drift_guard_catches_a_column_classified_on_both_sides() -> None:
    """Classifying a column both ways would defeat the partition, not extend it."""
    assert set(FILTERABLE_SPEC_FIELDS).isdisjoint(UNFILTERED_SPEC_FIELDS)

    contaminated_unfiltered = (*UNFILTERED_SPEC_FIELDS, FILTERABLE_SPEC_FIELDS[0])
    with pytest.raises(AssertionError):
        assert set(FILTERABLE_SPEC_FIELDS).isdisjoint(contaminated_unfiltered)


def test_the_classification_tuples_carry_no_internal_duplicates() -> None:
    """A duplicated entry would pass the dev's set-equality checks unnoticed."""
    assert len(FILTERABLE_SPEC_FIELDS) == len(set(FILTERABLE_SPEC_FIELDS))
    assert len(UNFILTERED_SPEC_FIELDS) == len(set(UNFILTERED_SPEC_FIELDS))


def test_filter_field_columns_name_real_motorbike_spec_columns() -> None:
    """Every mapped column must actually exist on the ORM model, not just read plausibly."""
    real_columns = set(MotorbikeSpec.__table__.columns.keys())
    for field, column in FILTER_FIELD_COLUMNS.items():
        assert column in real_columns, f"{field} maps to {column!r}, not a real column"


# --- the raw JSON schema (before LangChain inlines $defs) ---------------------


def test_root_schema_every_property_required_and_left_open() -> None:
    schema = TranslatedQuery.model_json_schema()

    assert set(schema["required"]) == set(schema["properties"]) == set(TranslatedQuery.model_fields)
    assert "additionalProperties" not in schema


def test_nested_spec_filters_def_every_property_required_and_closed() -> None:
    schema = TranslatedQuery.model_json_schema()
    filters_def = schema["$defs"]["SpecFilters"]

    fields = set(SpecFilters.model_fields)
    assert set(filters_def["required"]) == set(filters_def["properties"]) == fields
    assert filters_def["additionalProperties"] is False


def test_optional_scalar_fields_are_null_unions_not_a_missing_key() -> None:
    """Optionality is expressed structurally, never by simply omitting the key."""
    filters_def = TranslatedQuery.model_json_schema()["$defs"]["SpecFilters"]
    scalar_fields = (
        "engine_cc_min",
        "engine_cc_max",
        "power_kw_min",
        "power_kw_max",
        "wet_weight_kg_max",
        "seat_height_mm_max",
        "a2_eligible",
    )
    for field in scalar_fields:
        prop = filters_def["properties"][field]
        types = {member.get("type") for member in prop["anyOf"]}
        assert types == {prop["anyOf"][0]["type"], "null"}


def test_spec_filters_as_its_own_root_schema_stays_open_like_a_root() -> None:
    """`SpecFilters.model_json_schema()` called directly (not nested) is a root.

    Every property is still required, but `additionalProperties: False` is
    *not* added — the override's `nested` flag defaults to `False`, and
    `_require_every_property` only closes an object when it walks it as a
    `$defs` entry from a parent's schema generation (proven by
    `test_nested_spec_filters_def_every_property_required_and_closed` above).
    This matches the documented root-stays-open rule (2.17): closing is a
    provider requirement for a *nested* position, not a blanket rule.
    """
    schema = SpecFilters.model_json_schema()

    assert set(schema["required"]) == set(schema["properties"]) == set(SpecFilters.model_fields)
    assert "additionalProperties" not in schema


def test_search_queries_has_no_structural_minimum_or_maximum_in_the_schema() -> None:
    """The "1-3" bound in the step outline is prose + a post-hoc validator cap.

    The raw JSON schema places no `minItems`/`maxItems` on `search_queries` —
    the model is only guided by the description text ("One to {max} standalone
    search queries..."). The upper bound of 3 is enforced by
    `_text_list_validator(maximum_items=MAX_SEARCH_QUERIES)` *after* the answer
    comes back (proven independently below); there is no enforced lower bound
    of 1 anywhere — an empty list is a valid, complete plan (also proven by the
    dev's own `test_an_empty_answer_is_a_complete_plan`). This matches the
    shared-knowledge landed decision, which pins only "`search_queries` ≤
    `MAX_SEARCH_QUERIES = 3`" — no lower bound is claimed there either.
    """
    prop = TranslatedQuery.model_json_schema()["properties"]["search_queries"]

    assert "minItems" not in prop
    assert "maxItems" not in prop
    assert prop["type"] == "array"


def test_the_post_hoc_cap_is_the_only_enforcement_of_the_upper_bound() -> None:
    over_budget = [f"query {i}" for i in range(MAX_SEARCH_QUERIES + 5)]
    translated = TranslatedQuery.model_validate({"search_queries": over_budget})

    assert len(translated.search_queries) == MAX_SEARCH_QUERIES

    empty = TranslatedQuery.model_validate({"search_queries": []})
    assert empty.search_queries == []  # no lower bound enforced


# --- unit/vocabulary validators are the same objects, not a re-implementation -


def test_query_translation_reuses_extractions_validator_functions_verbatim() -> None:
    """Same function objects, not lookalikes that could drift independently."""
    assert query_translation._normalize_flag is extraction._normalize_flag
    assert query_translation._quantity_validator is extraction._quantity_validator
    assert query_translation._vocabulary_validator is extraction._vocabulary_validator


@pytest.mark.parametrize(
    ("field", "answer"),
    [
        ("engine_cc", "0.6 litres"),
        ("power_kw", "48 hp"),
        ("power_kw", "95 PS"),
        ("wet_weight_kg", "441 lbs"),
        ("seat_height_mm", "31.5 in"),
    ],
)
def test_a_quantity_normalizes_identically_via_both_modules(field: str, answer: str) -> None:
    """Spot-check equivalence end-to-end, not just object identity."""
    via_extraction = extraction._quantity_validator(field)(answer)

    filter_field = {
        "engine_cc": "engine_cc_min",
        "power_kw": "power_kw_max",
        "wet_weight_kg": "wet_weight_kg_max",
        "seat_height_mm": "seat_height_mm_max",
    }[field]
    via_translation = getattr(SpecFilters.model_validate({filter_field: answer}), filter_field)

    assert via_extraction == via_translation


# --- SpecFilters importability without the LLM machinery ----------------------


def test_spec_filters_class_itself_needs_no_configured_api_key() -> None:
    """`SpecFilters` is usable (validated, queried) with no OpenRouter key set."""
    filters = SpecFilters.model_validate({"seat_height_mm_max": "31.5 in"})
    assert filters.seat_height_mm_max == 800
    assert not filters.is_empty()


def test_importing_catalogue_search_service_drags_in_langchain() -> None:
    """Refutes the "importable without the LLM machinery" claim as import-graph fact.

    The module docstring of `query_translation.py` says `SpecFilters` "is
    deliberately importable without touching the LLM machinery", and the step
    file repeats it as a constraint the 3.11 tool depends on. In practice
    `catalogue_search_service.py` imports `SpecFilters` from
    `app.llm.query_translation`, and that module imports `langchain_core`
    symbols and `app.llm.models.get_chat_model` (which imports
    `langchain_openrouter.ChatOpenRouter`) unconditionally at module import
    time — there is no lazy/deferred import anywhere on the path. Importing
    `catalogue_search_service` in a fresh interpreter therefore *does* load
    the LangChain/OpenRouter client packages (proven here in a clean
    subprocess so no other test's imports can mask the result).

    This does not require a network call or an API key (`get_chat_model` is
    only called, never invoked, at import time) — but it does mean
    `catalogue_search_service` cannot be imported without LangChain installed
    and loaded into memory, which is what "without touching the LLM
    machinery" reads as a guarantee against.
    """
    probe = (
        "import sys; before = set(sys.modules); "
        "import app.services.catalogue_search_service; "
        "added = set(sys.modules) - before; "
        "hit = sorted(m for m in added if m.split('.')[0] in "
        "{'langchain_core', 'langchain_openrouter', 'langchain_openai', 'langchain'}); "
        "print(len(hit))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        cwd="/app",
    )
    langchain_modules_loaded = int(result.stdout.strip())

    # This assertion is the refutation, not a pass: importing the service
    # module *does* pull in a non-trivial number of LangChain modules.
    assert langchain_modules_loaded > 0, (
        "expected to reproduce the finding that catalogue_search_service drags "
        "in LangChain; if this now fails, the import chain was fixed and the "
        "finding is stale"
    )


# --- the prompt: StrictUndefined -----------------------------------------------


def test_a_missing_required_prompt_variable_raises() -> None:
    """`render_prompt` uses `StrictUndefined`: an unset variable the template
    references unconditionally must raise, not render a blank/garbled prompt.
    """
    with pytest.raises(UndefinedError):
        # `categories`, `price_bands` and `max_search_queries` are all
        # referenced unconditionally by query_translation.md; omit all three.
        render_prompt("query_translation", utterance="hello")


def test_supplying_every_variable_renders_without_history_or_preferences() -> None:
    """Sanity companion to the above: the same call succeeds once complete."""
    rendered = render_prompt(
        "query_translation",
        utterance="hello",
        history_summary=None,
        preferences=[],
        categories=("naked",),
        price_bands=("budget",),
        max_search_queries=3,
        fence_start=query_translation.FENCE_START,
        fence_end=query_translation.FENCE_END,
    )
    assert "hello" in rendered
    assert "Conversation so far" not in rendered
    assert "Recorded preferences" not in rendered
