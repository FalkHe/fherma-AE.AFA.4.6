"""`present_recommendations` — the advisor putting cards on the table.

The end of a consultation is a small set of concrete models with a reason each,
and this is how the advisor produces them: it names bikes and rationales, and the
tool turns them into the pinned `recommendations[]` snapshots the chat UI renders
as cards. Recommendations-via-tool is the pinned mechanism (over a second
structured-output pass): one loop, one capture, no post-hoc parsing of prose.

Four rules live here:

* **Only the catalogue may be recommended.** Every reference is resolved against
  *approved* entries (id, or name through the shared resolver). A name the
  catalogue does not know is **skipped**, not carried into a card — a card is a
  claim that this shop can advise on that bike. The skipped names come back in
  the result, so the model can correct itself in the same turn (and step 3.14's
  `flag_unknown_bike` is where they become an admin's problem).
* **The card is a snapshot, not a reference.** Plain users cannot read
  `/api/products` in this phase, so name, image URL and key specifications are
  copied in at write time; staleness is accepted (shared-knowledge pin).
* **The numbers are the verified ones or nothing.** `keySpecs` comes from
  `catalogue_search_service.get_verified_specs`; a specification the catalogue
  has not verified stays `null` and the card shows a gap.
* **The model gets an acknowledgement, not the snapshot.** What it needs to know
  is which cards the customer can now see, so it can write prose *around* them
  instead of repeating them.
"""

from typing import Any

from pydantic import ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from app.api.schemas.images import variant_urls
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.motorbike_image import ImageStatus
from app.llm.agents.tools import ToolContext, ToolModel, ToolSpec
from app.services import catalogue_search_service, naming_service, product_service
from app.services.naming_service import NameLevel

NAME = "present_recommendations"

# How many cards one call may show. A shortlist a customer can hold in their
# head, not a catalogue page.
MAX_RECOMMENDATIONS = 4

# A rationale is the one line under the card, and `matchedPreferences` are short
# labels ("A2 licence", "budget") — both are truncated rather than rejected, so a
# talkative model loses words, not the recommendation.
MAX_RATIONALE_CHARS = 300
MAX_MATCHED_PREFERENCES = 6
MAX_PREFERENCE_LABEL_CHARS = 60

# The image variant the card shows (the frontend derives the thumb from it).
CARD_VARIANT = "card"

DESCRIPTION = (
    "Show the customer recommendation cards for models from the curated "
    "catalogue. Call this once, near the end of the consultation, when the "
    f"interview and the tools support a shortlist: pass 1 to {MAX_RECOMMENDATIONS} "
    "models, each identified by catalogue id (motorbikeId) or name "
    "(motorbikeName), with a one-line rationale in the customer's language and "
    "the preferences it matches (short labels such as 'A2 licence' or 'seat "
    "height'). The card carries the model's picture and its verified key "
    "specifications automatically — write your prose around the cards instead of "
    "repeating those numbers. A model the catalogue does not know is skipped and "
    "named in the result: never present a bike you could not look up."
)


class RecommendationInput(ToolModel):
    """One model the advisor wants to recommend, as the model states it."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    motorbike_id: str | None = Field(
        default=None,
        description="Catalogue id of the model to recommend.",
    )
    motorbike_name: str | None = Field(
        default=None,
        description="Model name to recommend, as it was written in the conversation.",
    )
    rationale: str = Field(
        description="One line saying why this model fits this customer, in their language.",
    )
    matched_preferences: list[str] = Field(
        default_factory=list,
        description="Short labels of the customer's preferences this model satisfies.",
    )

    @field_validator("rationale")
    @classmethod
    def _normalize_rationale(cls, value: str) -> str:
        """Collapse whitespace, reject an empty rationale, truncate a long one."""
        text = " ".join(value.split())
        if not text:
            raise ValueError("Give a one-line rationale for the recommendation.")
        return text[:MAX_RATIONALE_CHARS]

    @field_validator("matched_preferences")
    @classmethod
    def _normalize_labels(cls, value: list[str]) -> list[str]:
        """Trim, drop blanks, deduplicate and cap the preference labels."""
        labels: list[str] = []
        for item in value:
            label = " ".join(item.split())[:MAX_PREFERENCE_LABEL_CHARS]
            if label and label not in labels:
                labels.append(label)
        return labels[:MAX_MATCHED_PREFERENCES]


class PresentRecommendationsArgs(ToolModel):
    """The shortlist to show."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    recommendations: list[RecommendationInput] = Field(
        min_length=1,
        max_length=MAX_RECOMMENDATIONS,
        description="The models to show as cards, best match first.",
    )


class PresentRecommendationsResult(ToolModel):
    """What the model is told: which cards exist now, and what could not be shown."""

    presented: list[str]
    skipped: list[str]
    message: str


async def run(ctx: ToolContext, args: PresentRecommendationsArgs) -> PresentRecommendationsResult:
    """Resolve, enrich and store the recommendation snapshots."""
    resolved: list[tuple[Motorbike, RecommendationInput]] = []
    skipped: list[str] = []
    seen: set[str] = set()

    for item in args.recommendations:
        reference = item.motorbike_id or item.motorbike_name or ""
        motorbike = await _resolve(ctx, item)
        if motorbike is None:
            skipped.append(reference)
            continue
        if motorbike.id in seen:
            continue
        seen.add(motorbike.id)
        resolved.append((motorbike, item))

    specs = await catalogue_search_service.get_verified_specs(
        ctx.session, [motorbike.id for motorbike, _ in resolved]
    )
    values = {entry.motorbike_id: entry.values for entry in specs}

    # The presented batch is each other's context, floored at the year range
    # (D5's binding per-caller table) — the cards on the table together are
    # exactly the set that must be told apart if two share a name.
    name_parts = await naming_service.load_name_parts(
        ctx.session, [motorbike.id for motorbike, _ in resolved]
    )
    names = naming_service.render_names(list(name_parts.values()), min_level=NameLevel.YEAR_RANGE)

    snapshots = [
        {
            "motorbikeId": motorbike.id,
            "name": names[motorbike.id],
            "imageUrl": await _card_image_url(ctx, motorbike.id),
            "rationale": item.rationale,
            "matchedPreferences": item.matched_preferences,
            "keySpecs": _key_specs(values.get(motorbike.id, {})),
        }
        for motorbike, item in resolved
    ]
    ctx.collector.record_recommendations(snapshots)

    return PresentRecommendationsResult(
        presented=[snapshot["name"] for snapshot in snapshots],
        skipped=skipped,
        message=_message(snapshots, skipped),
    )


async def _resolve(ctx: ToolContext, item: RecommendationInput) -> Motorbike | None:
    """Resolve one recommendation's reference to an approved entry, or `None`.

    Not `tools.resolve_references`: that helper stops the whole call at the first
    unresolvable reference, which is right for a comparison (a column would be
    missing) and wrong here (the other three cards are still good advice).
    """
    if item.motorbike_id:
        motorbike = await product_service.get_motorbike(ctx.session, item.motorbike_id)
        if motorbike is not None and motorbike.status is MotorbikeStatus.APPROVED:
            return motorbike
        return None
    if item.motorbike_name:
        return await catalogue_search_service.resolve_name(ctx.session, item.motorbike_name)
    return None


async def _card_image_url(ctx: ToolContext, motorbike_id: str) -> str | None:
    """Return the card-variant URL of the newest approved image, or `None`.

    The URL formula is the API layer's (`app.api.schemas.images`) and is reused
    rather than copied: the snapshot is served back verbatim as an attribute of
    `chat-messages`, so a second spelling of the same path would be a silently
    broken image. A model may well have no approved picture — that is a normal
    card without an image, never a placeholder.
    """
    images = await product_service.list_images(ctx.session, motorbike_id=motorbike_id)
    for image in images:  # newest first, the service's order
        if image.status is ImageStatus.APPROVED:
            return getattr(variant_urls(motorbike_id, image.id), CARD_VARIANT)
    return None


def _key_specs(values: dict[str, Any]) -> dict[str, Any]:
    """Return the pinned `keySpecs` object, every key present, unknowns `null`."""
    return {
        "category": values.get("category"),
        "engineCc": values.get("engine_cc"),
        "powerKw": values.get("power_kw"),
        "wetWeightKg": values.get("wet_weight_kg"),
        "seatHeightMm": values.get("seat_height_mm"),
        "priceBand": values.get("price_band"),
    }


def _message(snapshots: list[dict[str, Any]], skipped: list[str]) -> str:
    """Compose the one-line acknowledgement the model reads next."""
    if not snapshots:
        return (
            "No card was shown: none of these models is in the catalogue "
            f"({', '.join(skipped)}). Recommend models you have looked up instead."
        )

    names = ", ".join(str(snapshot["name"]) for snapshot in snapshots)
    shown = (
        f"The customer now sees {len(snapshots)} recommendation card(s) with picture and "
        f"verified specifications: {names}."
    )
    if skipped:
        shown += f" Not in the catalogue, so not shown: {', '.join(skipped)}."
    return shown


TOOL = ToolSpec(
    name=NAME,
    description=DESCRIPTION,
    args_schema=PresentRecommendationsArgs,
    run=run,
)
