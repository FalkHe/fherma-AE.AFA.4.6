"""Validation and caps for `motorbikes.type_codes` and `motorbikes.variants`.

The single place the two JSONB shapes' rules live, per
`docs/roadmap/model-naming-data-model.md` §2.4/§2.5. Both public functions
share one contract with `product_service._assign_manufacturer`'s precedent: a
value that fails validation is **dropped with a warning**, never an exception.
Nothing here writes to the database — callers (extraction, the API boundary)
decide what to do with `(kept, warnings)`.

`VARIANT_SPEC_KEYS` deliberately excludes `source_hints` and `extracted_at`
from `motorbike_spec.SPEC_FIELDS`: those two are per-extraction bookkeeping
about the *row*, not a property a trim can differ in. See
`docs/roadmap/phase-6/shared-knowledge.md` D1 for the adjudication — this is
not the `UNCOMPARED_SPEC_FIELDS` tuple in `catalogue_search_service.py`, which
also excludes `extra`; that tuple is not reused here.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.db.models.motorbike_spec import SPEC_FIELDS
from app.services import product_service

# `^[A-Z0-9]` + 1-31 more of `[A-Z0-9\-/ ]` = 2-32 characters total.
TYPE_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9\-/ ]{1,31}$")
MAX_TYPE_CODES = 8
MAX_VARIANTS = 20
VARIANT_NAME_LENGTH = 64
VARIANT_DESCRIPTION_LENGTH = 400

# Spec values a trim may carry a delta for, plus `extra`. Not extraction
# bookkeeping (see the module docstring).
VARIANT_SPEC_KEYS = tuple(f for f in SPEC_FIELDS if f not in ("source_hints", "extracted_at"))


class Variant(BaseModel):
    """One trim: a spec delta plus free text — never the base (§2.5).

    `slug` is always recomputed from `name` via `product_service.slugify` and
    never trusted from input, so it needs no caller-supplied value. `specs`
    keys are **not** restricted here — `normalize_variants` drops any key
    outside `VARIANT_SPEC_KEYS` after validation, keeping the entry (a key is
    dropped, not the variant).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    slug: str = ""
    name: str = Field(min_length=1, max_length=VARIANT_NAME_LENGTH)
    specs: dict[str, Any] = {}
    description: str = Field(default="", max_length=VARIANT_DESCRIPTION_LENGTH)

    @model_validator(mode="after")
    def _recompute_slug(self) -> "Variant":
        self.slug = product_service.slugify(self.name)
        return self


def normalize_type_codes(raw: Sequence[str]) -> tuple[list[str], list[str]]:
    """Return the type codes to keep, plus one warning per dropped entry.

    Each entry is trimmed and upper-cased, then dropped (with a warning) when
    it fails `TYPE_CODE_PATTERN`, is a duplicate already kept, or would push
    the list past `MAX_TYPE_CODES`. Order of the kept codes follows `raw`, but
    per §2.4 nothing may depend on it — the list is unordered metadata.
    """
    kept: list[str] = []
    warnings: list[str] = []
    for entry in raw:
        code = entry.strip().upper()
        if not TYPE_CODE_PATTERN.match(code):
            warnings.append(f"Dropped type code {entry!r}: does not match the required shape.")
            continue
        if code in kept:
            warnings.append(f"Dropped type code {code!r}: duplicate.")
            continue
        if len(kept) >= MAX_TYPE_CODES:
            warnings.append(
                f"Dropped type code {code!r}: at most {MAX_TYPE_CODES} type codes are kept."
            )
            continue
        kept.append(code)
    return kept, warnings


def normalize_variants(
    raw: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return the variants to keep, plus one warning per dropped entry or key.

    An entry failing the `Variant` model, a duplicate slug within the list, and
    an entry beyond `MAX_VARIANTS` each drop the whole entry. An unknown
    `specs` key drops only that key and keeps the entry. Order of the kept
    entries is preserved — it is the display order.
    """
    kept: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_slugs: set[str] = set()

    for entry in raw:
        try:
            variant = Variant.model_validate(entry)
        except ValidationError as error:
            warnings.append(f"Dropped variant {entry!r}: {_describe(error)}.")
            continue

        unknown_keys = sorted(set(variant.specs) - set(VARIANT_SPEC_KEYS))
        if unknown_keys:
            variant.specs = {
                key: value for key, value in variant.specs.items() if key in VARIANT_SPEC_KEYS
            }
            warnings.append(
                f"Dropped unknown spec key(s) {', '.join(unknown_keys)} from variant "
                f"{variant.name!r}."
            )

        if variant.slug in seen_slugs:
            warnings.append(f"Dropped variant {variant.name!r}: duplicate slug {variant.slug!r}.")
            continue
        if len(kept) >= MAX_VARIANTS:
            warnings.append(
                f"Dropped variant {variant.name!r}: at most {MAX_VARIANTS} variants are kept."
            )
            continue

        seen_slugs.add(variant.slug)
        kept.append(variant.model_dump())

    return kept, warnings


def _describe(error: ValidationError) -> str:
    """Render a `ValidationError` as one short, warning-ready sentence."""
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'variant'}: {item['msg']}"
        for item in error.errors()
    )
