"""`app/services/identity_validation.py` — the `type_codes`/`variants` caps.

Table-driven: every case that drops something asserts the warning it produced,
per the "`_assign_manufacturer` precedent" (shared-knowledge D1) — a bad entry
is dropped, never an exception.
"""

from app.services.identity_validation import (
    MAX_TYPE_CODES,
    MAX_VARIANTS,
    VARIANT_DESCRIPTION_LENGTH,
    VARIANT_NAME_LENGTH,
    VARIANT_SPEC_KEYS,
    normalize_type_codes,
    normalize_variants,
)

# --- normalize_type_codes ------------------------------------------------


def test_type_codes_are_trimmed_and_upper_cased() -> None:
    kept, warnings = normalize_type_codes([" k81 ", "sc82"])

    assert kept == ["K81", "SC82"]
    assert warnings == []


def test_type_codes_are_deduplicated_case_insensitively() -> None:
    kept, warnings = normalize_type_codes(["K81", "k81", " K81"])

    assert kept == ["K81"]
    assert len(warnings) == 2
    assert all("duplicate" in warning for warning in warnings)


def test_type_code_too_short_is_dropped_with_a_warning() -> None:
    kept, warnings = normalize_type_codes(["K"])

    assert kept == []
    assert len(warnings) == 1
    assert "'K'" in warnings[0]


def test_type_code_with_an_illegal_character_is_dropped_with_a_warning() -> None:
    kept, warnings = normalize_type_codes(["K81!"])

    assert kept == []
    assert len(warnings) == 1
    assert "K81!" in warnings[0]


def test_type_codes_are_capped_at_the_max_and_the_rest_warn() -> None:
    codes = [f"C{index:02d}" for index in range(MAX_TYPE_CODES + 1)]

    kept, warnings = normalize_type_codes(codes)

    assert kept == codes[:MAX_TYPE_CODES]
    assert len(warnings) == 1
    assert str(MAX_TYPE_CODES) in warnings[0]


def test_type_codes_keep_input_order() -> None:
    kept, _ = normalize_type_codes(["SC82", "K81"])

    assert kept == ["SC82", "K81"]


def test_no_type_codes_is_the_empty_result() -> None:
    assert normalize_type_codes([]) == ([], [])


# --- normalize_variants ---------------------------------------------------


def test_variant_slug_is_always_recomputed_from_name() -> None:
    kept, warnings = normalize_variants(
        [{"name": "Adventure", "slug": "not-trusted", "specs": {}, "description": ""}]
    )

    assert warnings == []
    assert len(kept) == 1
    assert kept[0]["slug"] == "adventure"
    assert kept[0]["name"] == "Adventure"


def test_variant_defaults_are_empty_specs_and_description() -> None:
    kept, warnings = normalize_variants([{"name": "Triple Black"}])

    assert warnings == []
    assert kept == [
        {"slug": "triple-black", "name": "Triple Black", "specs": {}, "description": ""}
    ]


def test_variant_name_over_the_cap_is_dropped_with_a_warning() -> None:
    too_long = "A" * (VARIANT_NAME_LENGTH + 1)

    kept, warnings = normalize_variants([{"name": too_long}])

    assert kept == []
    assert len(warnings) == 1
    assert "Dropped variant" in warnings[0]


def test_variant_description_over_the_cap_is_dropped_with_a_warning() -> None:
    kept, warnings = normalize_variants(
        [{"name": "Adventure", "description": "x" * (VARIANT_DESCRIPTION_LENGTH + 1)}]
    )

    assert kept == []
    assert len(warnings) == 1


def test_variant_missing_a_name_is_dropped_with_a_warning() -> None:
    kept, warnings = normalize_variants([{}])

    assert kept == []
    assert len(warnings) == 1


def test_unknown_spec_key_is_dropped_but_the_variant_is_kept() -> None:
    kept, warnings = normalize_variants(
        [{"name": "Adventure", "specs": {"wheelbase_mm": 1500, "tank_capacity_l": 30}}]
    )

    assert len(kept) == 1
    assert kept[0]["specs"] == {"tank_capacity_l": 30}
    assert len(warnings) == 1
    assert "wheelbase_mm" in warnings[0]


def test_every_allowed_spec_key_survives_the_whitelist() -> None:
    specs = dict.fromkeys(VARIANT_SPEC_KEYS, 1)

    kept, warnings = normalize_variants([{"name": "Adventure", "specs": specs}])

    assert warnings == []
    assert set(kept[0]["specs"]) == set(VARIANT_SPEC_KEYS)


def test_extraction_bookkeeping_keys_are_not_allowed_spec_keys() -> None:
    assert "source_hints" not in VARIANT_SPEC_KEYS
    assert "extracted_at" not in VARIANT_SPEC_KEYS
    assert "extra" in VARIANT_SPEC_KEYS


def test_duplicate_slug_within_the_list_drops_the_second_entry() -> None:
    kept, warnings = normalize_variants([{"name": "Adventure"}, {"name": "adventure"}])

    assert len(kept) == 1
    assert kept[0]["name"] == "Adventure"
    assert len(warnings) == 1
    assert "duplicate slug" in warnings[0]


def test_variants_are_capped_and_the_rest_warn() -> None:
    entries = [{"name": f"Trim {index}"} for index in range(MAX_VARIANTS + 1)]

    kept, warnings = normalize_variants(entries)

    assert len(kept) == MAX_VARIANTS
    assert [entry["name"] for entry in kept] == [f"Trim {index}" for index in range(MAX_VARIANTS)]
    assert len(warnings) == 1
    assert str(MAX_VARIANTS) in warnings[0]


def test_kept_variant_order_matches_input_order_after_a_drop() -> None:
    kept, warnings = normalize_variants(
        [{"name": "Adventure"}, {"name": "x" * (VARIANT_NAME_LENGTH + 1)}, {"name": "Sport"}]
    )

    assert [entry["name"] for entry in kept] == ["Adventure", "Sport"]
    assert len(warnings) == 1


def test_no_variants_is_the_empty_result() -> None:
    assert normalize_variants([]) == ([], [])
