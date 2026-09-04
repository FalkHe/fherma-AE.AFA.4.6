"""Schemas for the `catalogue-models` resource: the customer's view of the catalogue.

Wire shape is pinned by `docs/roadmap/stage-01/phase-4/shared-knowledge.md`: resource type
`catalogue-models`, camelCase attributes, **read-only** — there is deliberately
no request model at all (the 2b.3 `SpecAttributes` precedent), because nothing on
this surface is writable: the catalogue is curated through the admin resources.

Two attribute models, because the two routes deliberately answer different
shapes:

* `CatalogueModelSummaryAttributes` — one browse card. Scalars only, the eight
  summary specification values flattened next to the name, the brand and one
  image URL, so a page of cards is one JSON array a grid can render without
  further lookups. `slug`, `status`, `draftSpec`, `verifiedSpec` and the
  timestamps are **absent on purpose**: a customer neither sees curation state
  nor unreviewed numbers.
* `CatalogueModelAttributes` — the whole detail page in one document: the
  verified specification, the Wikipedia prose, the provenance list and the
  approved pictures.

`specs` carries exactly the 13 frozen comparison fields, `null` where the
catalogue has no verified number — never `extra`, `source_hints` or
`extracted_at`, which are extraction provenance and stay on the admin surface.
The drift guard in `tests/api/test_catalogue_models.py` asserts that parity
against `catalogue_search_service.COMPARISON_SPEC_FIELDS`.

`sources` carries a document's title and its external URL only: `contentMarkdown`
and `rawPath` are never served here — the one piece of prose a customer gets is
the Wikipedia `article`, everything else is a link out (see D4).

`CatalogueModelAttributes` also gains `variants` (step 6.20, ui-spec API-2): the
same `ProductVariant` wire shape the admin `products` resource uses — one shape,
imported rather than duplicated. It is **detail only**; the list resource gains
nothing. `suggestion` and `typeCodes` appear on **no** attribute of this module
— D6 — because the claim is never catalogue data and the type code is never
customer-visible.
"""

from typing import Literal

from app.api.jsonapi import Document, JsonApiModel, ListDocument, Resource
from app.api.schemas.images import ImageVariants
from app.api.schemas.products import PriceBand, ProductVariant, SpecCategory

CATALOGUE_MODEL_TYPE = "catalogue-models"


class CatalogueModelSpecs(JsonApiModel):
    """The verified specification of one model: the 13 frozen comparison fields.

    Field order mirrors `catalogue_search_service.COMPARISON_SPEC_FIELDS`, and
    every field is always present — `null` is the honest answer for a value the
    catalogue never verified, and the detail table renders the gap.
    """

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


class CatalogueSource(JsonApiModel):
    """One provenance entry: what a document is, and where it can be read."""

    source_title: str
    source_url: str | None


class CatalogueImage(ImageVariants):
    """One approved picture: the three variant URLs plus its attribution.

    Extends the pinned `ImageVariants` rather than restating the variant names,
    so the URL formula stays in one place. `attribution` travels with the URLs
    because the gallery must always render it — that is the licence compliance.
    """

    attribution: str | None


class CatalogueModelSummaryAttributes(JsonApiModel):
    """The pinned attribute set of one browse card."""

    name: str
    # Derived: the related manufacturer's name, `null` when none is assigned.
    manufacturer: str | None
    category: SpecCategory | None
    engine_cc: int | None
    power_kw: float | None
    wet_weight_kg: float | None
    seat_height_mm: int | None
    a2_eligible: bool | None
    price_band: PriceBand | None
    msrp_eur: int | None
    # `card` variant of the newest approved image; `null` when the model has
    # none (the client renders a placeholder, never a pending picture).
    image_url: str | None


class CatalogueModelAttributes(JsonApiModel):
    """The pinned attribute set of the detail page — self-contained on purpose."""

    name: str
    manufacturer: str | None
    specs: CatalogueModelSpecs
    # The Wikipedia document's markdown, or `null` when the model has none.
    article: str | None
    sources: list[CatalogueSource]
    images: list[CatalogueImage]
    # Detail only (D6, ui-spec API-2) — every trim of this generation except
    # the base, which is this resource itself.
    variants: list[ProductVariant]


class CatalogueModelSummaryResource(Resource[CatalogueModelSummaryAttributes]):
    """A catalogue-model resource object as it appears in the list."""

    type: Literal["catalogue-models"] = CATALOGUE_MODEL_TYPE


class CatalogueModelResource(Resource[CatalogueModelAttributes]):
    """A catalogue-model resource object as it appears in the detail document."""

    type: Literal["catalogue-models"] = CATALOGUE_MODEL_TYPE


class CatalogueModelDocument(Document[CatalogueModelResource]):
    """Body of `GET /api/catalogue-models/{motorbike_id}`."""


class CatalogueModelListDocument(ListDocument[CatalogueModelSummaryResource]):
    """Body of `GET /api/catalogue-models`."""
