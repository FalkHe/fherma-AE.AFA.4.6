from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class ContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


ContentId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
ProseText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Abilities(ContentModel):
    strength: int = Field(ge=1, le=30)
    dexterity: int = Field(ge=1, le=30)
    constitution: int = Field(ge=1, le=30)
    intelligence: int = Field(ge=1, le=30)
    wisdom: int = Field(ge=1, le=30)
    charisma: int = Field(ge=1, le=30)


class Attack(ContentModel):
    name: ProseText
    to_hit: int
    damage: ProseText


class StatBlock(ContentModel):
    max_hp: int = Field(ge=1)
    armour_class: int = Field(ge=1)
    abilities: Abilities
    attacks: list[Attack] = Field(default_factory=list)
    traits: list[ProseText] = Field(default_factory=list)


class ObjectTemplateBase(ContentModel):
    id: ContentId
    kind: str
    name: ProseText
    description: ProseText


class CreatureTemplate(ObjectTemplateBase):
    kind: Literal["creature"]
    disposition: ProseText
    stat_block: StatBlock


class ItemTemplate(ObjectTemplateBase):
    kind: Literal["item"]
    attacks: list[Attack] = Field(default_factory=list)


class FixtureCheck(ContentModel):
    action: ProseText
    dc: int = Field(ge=1, le=30)
    success: ProseText
    bypassed_by: list[ContentId] = Field(default_factory=list)


class FixtureTemplate(ObjectTemplateBase):
    kind: Literal["fixture"]
    checks: list[FixtureCheck] = Field(min_length=1)


ObjectTemplate = Annotated[
    CreatureTemplate | ItemTemplate | FixtureTemplate,
    Field(discriminator="kind"),
]


class Secret(ContentModel):
    fact: ProseText
    dc: int = Field(ge=1, le=30)
    discovered_by: ProseText


class Carried(ContentModel):
    template: ContentId
    count: int = Field(default=1, ge=1)


class Placement(ContentModel):
    template: ContentId
    count: int = Field(default=1, ge=1)
    carries: list[Carried] = Field(default_factory=list)


class Exit(ContentModel):
    id: ContentId
    kind: Literal["scene", "adventure_end"] = "scene"
    to: ContentId | None = None
    description: ProseText
    condition: ProseText | None = None

    @model_validator(mode="after")
    def _to_matches_kind(self) -> Self:
        if self.kind == "scene" and self.to is None:
            raise ValueError("to is required when kind is 'scene'")
        if self.kind == "adventure_end" and self.to is not None:
            raise ValueError("to must be absent when kind is 'adventure_end'")
        return self


class Scene(ContentModel):
    id: ContentId
    title: ProseText
    truth: list[ProseText] = Field(min_length=1)
    npc_intent: ProseText | None = None
    consequences: list[ProseText] = Field(default_factory=list)
    hidden: list[Secret] = Field(default_factory=list)
    placements: list[Placement] = Field(default_factory=list)
    exits: list[Exit] = Field(default_factory=list)
    pressure: ProseText | None = None


class Adventure(ContentModel):
    id: ContentId
    title: ProseText
    intro: ProseText
    entry_scene: ContentId
    scenes: list[Scene] = Field(min_length=1)


class SeedCharacter(ContentModel):
    name: ProseText
    race: ProseText
    character_class: ProseText
    background: ProseText
    appearance: ProseText
    abilities: Abilities
    max_hp: int = Field(ge=1)
    armour_class: int = Field(ge=1)
    inventory: list[ContentId] = Field(default_factory=list)


class Campaign(ContentModel):
    id: ContentId
    title: ProseText
    summary: ProseText
    adventures: list[ContentId] = Field(min_length=1)
    seed_character: SeedCharacter
    object_templates: list[ObjectTemplate] = Field(min_length=1)


class LoadedCampaign(ContentModel):
    campaign: Campaign
    version: str
    adventures: dict[str, Adventure]
    scenes: dict[str, Scene]
    object_templates: dict[str, ObjectTemplate]
