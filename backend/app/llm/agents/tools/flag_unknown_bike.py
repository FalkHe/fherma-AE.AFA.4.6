"""`flag_unknown_bike` — a model the catalogue does not know, noted for research.

The curated catalogue is the whole point of this advisor: it only advises on what
it has verified, so `{"unknownBike": …}` is a normal outcome of every bike-taking
tool. What this tool adds is the other half of that answer — the shop gets to
*learn* what customers ask for. The name lands as a `backlog` row, which is
exactly where an admin's ingestion run starts (`POST /api/products`, `app ingest`),
so a demand signal becomes a catalogue entry without anybody transcribing it.

Two properties, and they are the whole tool:

* **Idempotent across every status.** `product_service.create_backlog` derives the
  slug and raises `DuplicateModelError` when *any* catalogue row already owns it —
  `backlog`, `ingesting`, `approved`, `rejected` alike. Catching that is what
  makes repeated mentions one row and an approved model `already_known` rather
  than a duplicate that would later collide with its own slug. Deduplication is
  the **slug's**, not the tool's: `" Suzuki  GSR 600 "` and `"SUZUKI GSR 600!"`
  are one entry, while a differently *spaced* name ("Suzuki GSR600") is a
  different slug and therefore a different entry — exactly as the admin create
  path treats it. The tool deliberately invents no fuzzier identity: the cost of
  the boundary is a redundant backlog row an admin discards, and inventing one
  would silently swallow genuinely new models.
* **It writes a name, nothing else.** No status transition, no ingestion enqueue —
  a customer's mention is a suggestion, and starting a paid ingestion run off one
  is an admin's decision. Together with `record_preference` these are the two
  explicitly permitted autonomous writes (shared-knowledge §Agent-loop
  decisions); no other write reaches the database from a tool.

The result tells the model which of the two happened, so it can answer honestly
("I have noted it for our buyers" vs. "it is already on our list").
"""

from pydantic import ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from app.db.models.motorbike import NAME_LENGTH
from app.llm.agents.tools import ToolContext, ToolModel, ToolSpec
from app.services import product_service

NAME = "flag_unknown_bike"

# The two `status` values of the pinned result shape.
QUEUED = "queued"
ALREADY_KNOWN = "already_known"

DESCRIPTION = (
    "Note a motorcycle model the catalogue does not know, so the shop can research "
    'and add it. Call it after a tool answered {"unknownBike": "<name>"} and the '
    "customer would like the model looked into: pass the model name as it was "
    "written, including the make ('Suzuki GSR 600'). The result says whether the "
    "name was queued for research ('queued') or was already on the list "
    "('already_known') — either way it is recorded exactly once, so a second call "
    "for the same model creates nothing. This does not make the model available: "
    "you still cannot advise on it in this conversation, and you must not promise "
    "when it will be added."
)


class FlagUnknownBikeArgs(ToolModel):
    """The model name to note."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    name: str = Field(
        description="The model name as it was written in the conversation, make included.",
    )

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        """Collapse whitespace, truncate to the column width, reject a non-name.

        A name that slugifies to nothing ("???", "—") is not a model: it would
        become a catalogue row with an empty slug, and the *next* such mention
        would silently be `already_known`. Rejecting it is an argument error the
        model can react to.
        """
        text = " ".join(value.split())[:NAME_LENGTH]
        if not product_service.slugify(text):
            raise ValueError("Give the model name as written, e.g. 'Suzuki GSR 600'.")
        return text


class FlagUnknownBikeResult(ToolModel):
    """The pinned acknowledgement: the name, and whether it was new."""

    name: str
    status: str


async def run(ctx: ToolContext, args: FlagUnknownBikeArgs) -> FlagUnknownBikeResult:
    """Add `name` to the backlog, or report that the catalogue already has it."""
    try:
        await product_service.create_backlog(ctx.session, args.name)
    except product_service.DuplicateModelError:
        return FlagUnknownBikeResult(name=args.name, status=ALREADY_KNOWN)

    return FlagUnknownBikeResult(name=args.name, status=QUEUED)


TOOL = ToolSpec(
    name=NAME,
    description=DESCRIPTION,
    args_schema=FlagUnknownBikeArgs,
    run=run,
)
