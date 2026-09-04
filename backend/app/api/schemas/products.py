"""Schemas for the `products` resource.

Wire shape is pinned by `docs/roadmap/stage-01/phase-2/shared-knowledge.md`: resource
type `products`, camelCase attributes, specification objects mirroring the
frozen column set (`null` when the model has no such revision).

`manufacturer` is the one attribute that is **derived** rather than a column: it
carries the name of the related `manufacturers` row (`null` when the model has
no brand assigned), which the endpoint resolves — see
`docs/roadmap/stage-01/phase-2b/shared-knowledge.md`. The shape is unchanged by that.

Two specification models on purpose:

* `SpecAttributes` is what a specification looks like on the way *out* — no
  range constraints, because it renders whatever the database holds;
* `DraftSpecRequest` is what an admin may write. It carries the boundary
  validation (positive numbers, column ranges, the pinned category and
  price-band vocabularies) and rejects unknown keys, so
  `product_service.upsert_draft_spec` never sees a field outside the frozen set
  (that would be a bug there, not user input).

`verifiedSpec` is read-only everywhere: approval promotes a draft, and no API
path writes a `verified` row. `extra="forbid"` on the request models is what
turns a `verifiedSpec` in a PATCH body into a 422 instead of a silent no-op.

Step 6.20 (`docs/roadmap/stage-01/phase-6/shared-knowledge.md`) adds the identity block,
additively (D6/D10): `queryName`, `buildingline`, `typeCodes`, `variants` and
`suggestion` on `ProductAttributes`; a writable `identity` block
(`IdentityRequest`) on `ProductPatchAttributes`, applied through
`product_service.assign_identity` — the **only** writer of those columns (D2).
`IdentityRequest` reuses `identity_validation`'s `Variant` model and its
`TYPE_CODE_PATTERN`/`MAX_TYPE_CODES`/`MAX_VARIANTS` caps rather than restating
them. `suggestion` (`ProductSuggestion`) is the unverified claim JSONB
camelCased for the wire (D6) — never written by this schema, read-only,
unknown keys ignored rather than rejected because it is stored JSON.
"""

import json
import string
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.jsonapi import Document, JsonApiModel, ListDocument, Resource
from app.db.models.motorbike import (
    BUILDINGLINE_LENGTH,
    MODEL_NAME_LENGTH,
    NAME_LENGTH,
    MotorbikeStatus,
)
from app.db.models.motorbike_spec import PRICE_BANDS, SPEC_CATEGORIES
from app.services import identity_validation

PRODUCT_TYPE = "products"

# Column ceilings, so an out-of-range value is a 422 at the boundary instead of
# a database error further in. See the frozen column set in the ORM model.
SMALLINT_MAX = 32_767
INTEGER_MAX = 2_147_483_647
NUMERIC_5_1_MAX = 9_999.9
NUMERIC_4_1_MAX = 999.9

# `extra`/`source_hints` are open objects (the extraction model's long tail) —
# without a bound a hallucinated or adversarial payload could grow the JSONB
# column unboundedly.
DRAFT_SPEC_EXTRA_MAX_KEYS = 50
DRAFT_SPEC_EXTRA_KEY_MAX_LENGTH = 64
DRAFT_SPEC_EXTRA_VALUE_MAX_LENGTH = 2_000

# What `product_service.slugify` keeps; a name without one of these has no
# identity to be unique on.
SLUG_CHARACTERS = frozenset(string.ascii_lowercase + string.digits)

# `IdentityRequest.year_from`/`year_to` bounds (ui-spec §1.3): the first
# production motorcycle predates 1900, so this is a wider window than
# extraction's own plausibility check (`app.llm.extraction.YEAR_MIN` is 1900)
# — the two are deliberately different constants for different purposes.
IDENTITY_YEAR_MIN = 1885

# The pinned vocabularies as enums, so they reach OpenAPI (and therefore the
# review form's select options) instead of being free text. Built from the
# single source of truth in the ORM model — they cannot drift.
SpecCategory = StrEnum("SpecCategory", {value.upper(): value for value in SPEC_CATEGORIES})
PriceBand = StrEnum("PriceBand", {value.upper(): value for value in PRICE_BANDS})


class SpecAttributes(JsonApiModel):
    """One specification revision of a product, as returned."""

    # Built straight from the ORM row.
    model_config = ConfigDict(from_attributes=True)

    category: SpecCategory | None
    engine_cc: int | None
    cylinders: int | None
    power_kw: float | None
    torque_nm: float | None
    wet_weight_kg: float | None
    seat_height_mm: int | None
    tank_capacity_l: float | None
    top_speed_kmh: int | None
    abs: bool | None
    a2_eligible: bool | None
    price_band: PriceBand | None
    msrp_eur: int | None
    extra: dict[str, Any]
    source_hints: dict[str, Any] | None
    extracted_at: datetime | None


class ProductVariant(JsonApiModel):
    """One trim, as returned: a spec delta plus free text (D1/D2, §2.5).

    `specs` keys stay the snake_case frozen spec column names verbatim — they
    are data stored in the row's JSONB, not schema fields, so they are never
    camelCased.
    """

    slug: str
    name: str
    description: str | None
    specs: dict[str, Any] | None


class SuggestionYearRange(JsonApiModel):
    """One `(from, to)` pair out of a suggestion's claimed year ranges.

    `from` is a Python keyword, hence the `from_` field name with an explicit
    alias — the one place in this module the alias generator's default
    (`to_camel("from_") == "from_"`, verified: it does not strip a trailing
    underscore) would get it wrong.
    """

    from_: Annotated[int | None, Field(alias="from")] = None
    to: int | None = None


class ProductSuggestion(JsonApiModel):
    """The unverified claim `motorbikes.suggestion` carries, camelCased (D6).

    Never written by any schema in this module — only a human "using the
    claim" in the review form copies a value into the typed `identity` block,
    and that goes through `IdentityRequest` like any other admin edit. Unknown
    keys are ignored, never rejected: this projects a stored JSON document,
    not a request body.
    """

    source: str
    raw: str
    manufacturer: str | None
    model: str | None
    year_from: int | None
    year_to: int | None
    in_production: bool
    year_ranges: list[SuggestionYearRange]
    type_codes: list[str]
    links: list[str]


class ProductAttributes(JsonApiModel):
    """The pinned attribute set of a product.

    `buildingline` and `suggestion` carry an explicit `None` default even
    though nothing here ever *omits* them (`endpoints/products.py::_resource`
    always supplies a value): FastAPI's exported OpenAPI schema drops the
    `default` key for a field whose default is `None` and whose type already
    allows `null`, which keeps those two out of the `required` list and, in
    turn, keeps the generated TypeScript member optional (`?:`) rather than
    mandatory — so a `Product`-typed fixture written before this step (there
    are several, across the frontend) stays structurally valid without an
    edit. The other three additions (`queryName`, `typeCodes`, `variants`)
    cannot take the same shortcut honestly: they are never actually absent or
    `null` on a real row, so giving them a non-`None` default would still
    leave them required in the generated type (FastAPI keeps a non-`None`
    default in the schema, and `openapi-typescript`'s `defaultNonNullable`
    forces a defaulted-but-present field back to required) while also
    misstating what the wire actually sends. They stay required, matching
    every other non-nullable field this model already has.
    """

    name: str
    slug: str
    query_name: str
    # Derived: the related manufacturer's name, `null` when none is assigned.
    manufacturer: str | None
    buildingline: str | None = None
    model_name: str | None
    year_from: int | None
    year_to: int | None
    type_codes: list[str]
    variants: list[ProductVariant]
    # `null` when the row was never proposed from a suggestion list (D6).
    suggestion: ProductSuggestion | None = None
    status: MotorbikeStatus
    draft_spec: SpecAttributes | None
    verified_spec: SpecAttributes | None
    created_at: datetime
    updated_at: datetime


class ProductResource(Resource[ProductAttributes]):
    """A product resource object."""

    type: Literal["products"] = PRODUCT_TYPE


class ProductDocument(Document[ProductResource]):
    """Body of `GET`/`POST`/`PATCH` on a single product."""


class ProductListDocument(ListDocument[ProductResource]):
    """Body of `GET /api/products`."""


class DraftSpecRequest(JsonApiModel):
    """A full draft specification: every omitted field is reset.

    Full-object replace is the pinned semantics — the SPA merges the last
    fetched `draftSpec` with its form values before sending, so fields the form
    does not show survive a save.
    """

    model_config = ConfigDict(extra="forbid")

    category: SpecCategory | None = None
    engine_cc: Annotated[int | None, Field(gt=0, le=INTEGER_MAX)] = None
    cylinders: Annotated[int | None, Field(gt=0, le=SMALLINT_MAX)] = None
    power_kw: Annotated[float | None, Field(gt=0, le=NUMERIC_5_1_MAX)] = None
    torque_nm: Annotated[float | None, Field(gt=0, le=NUMERIC_5_1_MAX)] = None
    wet_weight_kg: Annotated[float | None, Field(gt=0, le=NUMERIC_5_1_MAX)] = None
    seat_height_mm: Annotated[int | None, Field(gt=0, le=SMALLINT_MAX)] = None
    tank_capacity_l: Annotated[float | None, Field(gt=0, le=NUMERIC_4_1_MAX)] = None
    top_speed_kmh: Annotated[int | None, Field(gt=0, le=SMALLINT_MAX)] = None
    abs: bool | None = None
    # An explicit value always wins; null lets the service derive it.
    a2_eligible: bool | None = None
    price_band: PriceBand | None = None
    msrp_eur: Annotated[int | None, Field(gt=0, le=INTEGER_MAX)] = None
    extra: dict[str, Any] | None = None
    source_hints: dict[str, Any] | None = None
    extracted_at: datetime | None = None

    @field_validator("extra", "source_hints")
    @classmethod
    def check_extra_size(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Cap the open object's key count, key length and per-value size.

        The ranges are arbitrary but generous for a genuine extraction long
        tail; they exist to catch a runaway payload, not a legitimate one.
        """
        if value is None:
            return value
        if len(value) > DRAFT_SPEC_EXTRA_MAX_KEYS:
            raise ValueError(f"Must have at most {DRAFT_SPEC_EXTRA_MAX_KEYS} keys.")
        for key, item in value.items():
            if len(key) > DRAFT_SPEC_EXTRA_KEY_MAX_LENGTH:
                raise ValueError(
                    f"Key '{key}' exceeds {DRAFT_SPEC_EXTRA_KEY_MAX_LENGTH} characters."
                )
            if len(json.dumps(item, default=str)) > DRAFT_SPEC_EXTRA_VALUE_MAX_LENGTH:
                raise ValueError(
                    f"Value for key '{key}' exceeds "
                    f"{DRAFT_SPEC_EXTRA_VALUE_MAX_LENGTH} characters when serialized."
                )
        return value


class ProductCreateAttributes(JsonApiModel):
    """The single attribute a new catalogue entry is created from."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=NAME_LENGTH,
            description='Display name as entered, e.g. "Suzuki GSR 600".',
        ),
    ]

    @field_validator("name")
    @classmethod
    def check_name_has_slug_characters(cls, value: str) -> str:
        """Trim the name and reject one the slugifier would reduce to nothing."""
        stripped = value.strip()
        if not SLUG_CHARACTERS & set(stripped.lower()):
            raise ValueError("Name must contain at least one ASCII letter or digit.")
        return stripped


class IdentityRequest(JsonApiModel):
    """The writable identity block: a full-object replace (D2), never a merge.

    Boundary caps reuse 6.10's `identity_validation` module rather than
    restating its regex/caps: `variants` entries are validated by its
    `Variant` model (name length, description length — `slug` is never
    trusted from input, `identity_validation.Variant` always recomputes it),
    and `type_codes`/`variants` are capped at
    `identity_validation.MAX_TYPE_CODES`/`MAX_VARIANTS`. The year bounds
    (`IDENTITY_YEAR_MIN` through the current year plus two) and the
    `yearTo >= yearFrom` pair check are this schema's own — `assign_identity`
    itself does not check plausibility, only shape.

    An entry `assign_identity`'s own `identity_validation` pass would drop
    (an unknown `specs` key, a duplicate slug, a type code past the cap) is
    still accepted **here** and silently dropped there with a `logger.warning`
    — this schema's checks are a stricter, earlier subset for immediate
    feedback, not a second implementation of the same rules.
    """

    model_config = ConfigDict(extra="forbid")

    manufacturer_id: str | None = None
    buildingline: Annotated[str | None, Field(max_length=BUILDINGLINE_LENGTH)] = None
    model_name: Annotated[str | None, Field(max_length=MODEL_NAME_LENGTH)] = None
    year_from: int | None = None
    year_to: int | None = None
    type_codes: Annotated[list[str], Field(max_length=identity_validation.MAX_TYPE_CODES)] = []
    variants: Annotated[
        list[identity_validation.Variant], Field(max_length=identity_validation.MAX_VARIANTS)
    ] = []

    @field_validator("year_from", "year_to")
    @classmethod
    def check_year_bounds(cls, value: int | None) -> int | None:
        """Reject a year outside `[IDENTITY_YEAR_MIN, current year + 2]`."""
        if value is None:
            return value
        year_max = datetime.now(UTC).year + 2
        if not IDENTITY_YEAR_MIN <= value <= year_max:
            raise ValueError(f"Must be between {IDENTITY_YEAR_MIN} and {year_max}.")
        return value

    @field_validator("type_codes")
    @classmethod
    def check_type_codes_shape(cls, value: list[str]) -> list[str]:
        """Reject a type code that does not match `TYPE_CODE_PATTERN`."""
        for code in value:
            if not identity_validation.TYPE_CODE_PATTERN.match(code):
                raise ValueError(f"Type code {code!r} does not match the required shape.")
        return value

    @model_validator(mode="after")
    def check_year_pair(self) -> "IdentityRequest":
        """Reject `yearTo` before `yearFrom` when both are set."""
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_to < self.year_from
        ):
            raise ValueError("yearTo must not be before yearFrom.")
        return self


class ProductPatchAttributes(JsonApiModel):
    """The writable attributes of an existing product.

    All three are optional; `verifiedSpec` (and anything else) is rejected
    outright. Applied by the endpoint in a fixed order — identity, then draft
    specification, then status (D2) — documented on `update_product` itself.
    """

    model_config = ConfigDict(extra="forbid")

    status: MotorbikeStatus | None = Field(
        default=None,
        description="Target status; must be legal for the current one.",
    )
    draft_spec: DraftSpecRequest | None = Field(
        default=None,
        description="Full replacement of the draft specification.",
    )
    identity: IdentityRequest | None = Field(
        default=None,
        description="Full replacement of the identity block (D2).",
    )


class ProductCreateResource(BaseModel):
    """The resource object of a create request."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["products"] = PRODUCT_TYPE
    attributes: ProductCreateAttributes


class ProductPatchResource(BaseModel):
    """The resource object of an update request."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["products"] = PRODUCT_TYPE
    attributes: ProductPatchAttributes


class ProductCreateRequest(BaseModel):
    """Body of `POST /api/products`."""

    model_config = ConfigDict(extra="forbid")

    data: ProductCreateResource


class ProductPatchRequest(BaseModel):
    """Body of `PATCH /api/products/{id}`."""

    model_config = ConfigDict(extra="forbid")

    data: ProductPatchResource
