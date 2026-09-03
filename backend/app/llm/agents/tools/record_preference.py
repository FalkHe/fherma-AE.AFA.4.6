"""`record_preference` — the interview's memory, one captured answer at a time.

The advisor asks six things (experience, licence, use case, budget, physique,
preferences) over as many turns as the customer needs, and the model's context is
rebuilt from the stored timeline on every one of them. This tool is what makes
that memory *structured*: each answer becomes a `chat_preferences` row with a
firmness, and `advisor.build_context` renders the still-active rows as a block of
the system prompt — so the next turn starts from what the customer said, in the
customer's own terms, without the model having to re-derive it from the prose.

Three decisions live here:

* **Supersession belongs to the service, not to the tool.**
  `chat_service.record_preference` inserts the new row and points the previous
  active one at it in one transaction (3.1). A customer who says "actually, max
  5000" is not a contradiction to resolve in a prompt — it is one more capture,
  and the history of the changing mind stays in the table.
* **The attribute is normalized, the value is not.** Supersession matches on the
  exact `attribute` string, so `"Budget"`, `"budget"` and `"budget_eur"`… would
  otherwise pile up as three active preferences that all mean the same thing.
  `_normalize_attribute` lower-cases and collapses separators to single spaces;
  the *value* is stored as the model phrased it, because that is what the next
  turn's prompt shows and the wording carries meaning ("around 6000 €").
* **This is one of the two explicitly permitted autonomous writes**
  (shared-knowledge §Agent-loop decisions, with `flag_unknown_bike`): a
  chat-scoped note about the conversation it happens in, invisible to anybody
  else, with no confirmation flow. It therefore needs the chat — the `app tools
  run` harness has none and gets a plain refusal rather than an invented one.
"""

import re

from pydantic import ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from app.db.models.chat import ATTRIBUTE_LENGTH, VALUE_LENGTH, PreferenceFirmness
from app.llm.agents.tools import ToolContext, ToolModel, ToolSpec
from app.services import chat_service

NAME = "record_preference"

# Whitespace, underscores and hyphens all separate words of an attribute name:
# "use case", "use_case" and "Use-Case" are the same thing to capture, and
# collapsing them is what lets a later answer supersede an earlier one.
_ATTRIBUTE_SEPARATORS = re.compile(r"[\s_-]+")

# The vocabulary the interview suggests. Not enforced anywhere (the column is a
# plain string on purpose — a consultation may learn something nobody
# anticipated), but naming it in the description keeps the captures stable enough
# for supersession to work.
SUGGESTED_ATTRIBUTES = (
    "experience",
    "licence",
    "use case",
    "budget",
    "height",
    "inside leg",
    "style",
    "brand",
    "luggage",
    "pillion",
)

DESCRIPTION = (
    "Remember one thing the customer told you about themselves or about what they "
    "want, so the next turns of this consultation build on it. Call it once per "
    "fact, in the turn the customer states it. attribute is a short lower-case "
    f"name — prefer these: {', '.join(SUGGESTED_ATTRIBUTES)}. value is what the "
    "customer said, in their words ('around 6000 €', 'A2', 'daily 20 km "
    "commute'). firmness is how binding it is: 'hard' for a constraint you may "
    "not violate (licence class, a budget ceiling, a deal-breaker), 'soft' for a "
    "leaning, 'exploring' for something being tried on. Capturing the same "
    "attribute again replaces the earlier answer automatically, which is how a "
    "customer changes their mind — so re-record instead of arguing, and never ask "
    "again for something you already recorded."
)


class MissingChatError(RuntimeError):
    """Raised when this tool runs outside a consultation.

    A preference is chat-scoped; there is nothing to attach it to in the `app
    tools run` harness. The loop turns this into a `failed` tool call the model is
    told about, which cannot happen in production — a turn always has its chat.
    """

    def __init__(self) -> None:
        super().__init__("record_preference needs a consultation; this context has no chat.")


class RecordPreferenceArgs(ToolModel):
    """What was learned, and how firmly it was said."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    attribute: str = Field(
        description="Short lower-case name of what was learned, e.g. 'budget' or 'licence'.",
    )
    value: str = Field(
        description="What the customer said, in their own words.",
    )
    firmness: PreferenceFirmness = Field(
        description="How binding it is: hard (a constraint), soft (a leaning), exploring.",
    )

    @field_validator("attribute")
    @classmethod
    def _normalize_attribute(cls, value: str) -> str:
        """Lower-case, collapse separators, reject a blank name, truncate a long one."""
        text = _ATTRIBUTE_SEPARATORS.sub(" ", value.lower()).strip()
        if not text:
            raise ValueError("Name what was learned, e.g. 'budget'.")
        return text[:ATTRIBUTE_LENGTH]

    @field_validator("value")
    @classmethod
    def _normalize_value(cls, value: str) -> str:
        """Collapse whitespace, reject a blank value, truncate a long one."""
        text = " ".join(value.split())
        if not text:
            raise ValueError("Say what the customer stated, e.g. 'around 6000 €'.")
        return text[:VALUE_LENGTH]


class RecordPreferenceResult(ToolModel):
    """The pinned acknowledgement: exactly what was stored.

    The attribute comes back **normalized**, so the model sees the name the next
    capture has to reuse for the supersession to hit.
    """

    attribute: str
    value: str
    firmness: str


async def run(ctx: ToolContext, args: RecordPreferenceArgs) -> RecordPreferenceResult:
    """Store the preference (superseding the previous answer) and acknowledge it.

    Raises:
        MissingChatError: there is no consultation to attach the preference to.
    """
    if ctx.chat is None:
        raise MissingChatError

    preference = await chat_service.record_preference(
        ctx.session,
        ctx.chat.id,
        attribute=args.attribute,
        value=args.value,
        firmness=args.firmness,
    )
    return RecordPreferenceResult(
        attribute=preference.attribute,
        value=preference.value,
        firmness=preference.firmness.value,
    )


TOOL = ToolSpec(
    name=NAME,
    description=DESCRIPTION,
    args_schema=RecordPreferenceArgs,
    run=run,
)
