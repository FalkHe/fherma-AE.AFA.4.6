from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


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


class Definition(ContentModel):
    id: ContentId
    name: ProseText
    description: ProseText
    disposition: ProseText
    stat_block: StatBlock


class Secret(ContentModel):
    fact: ProseText
    dc: int = Field(ge=1, le=30)
    discovered_by: ProseText


class CreaturePlacement(ContentModel):
    definition: ContentId
    count: int = Field(default=1, ge=1)


class Exit(ContentModel):
    to: ContentId
    description: ProseText
    condition: ProseText | None = None


class Scene(ContentModel):
    id: ContentId
    title: ProseText
    truth: list[ProseText] = Field(min_length=1)
    npc_intent: ProseText | None = None
    consequences: list[ProseText] = Field(default_factory=list)
    hidden: list[Secret] = Field(default_factory=list)
    creatures: list[CreaturePlacement] = Field(default_factory=list)
    exits: list[Exit] = Field(default_factory=list)
    pressure: ProseText | None = None


class Adventure(ContentModel):
    id: ContentId
    title: ProseText
    intro: ProseText
    entry_scene: ContentId
    scenes: list[ContentId] = Field(min_length=1)


class SeedCharacter(ContentModel):
    name: ProseText
    race: ProseText
    character_class: ProseText
    background: ProseText
    appearance: ProseText
    abilities: Abilities
    max_hp: int = Field(ge=1)
    armour_class: int = Field(ge=1)
    inventory: list[ProseText] = Field(default_factory=list)


class Campaign(ContentModel):
    id: ContentId
    title: ProseText
    summary: ProseText
    adventures: list[ContentId] = Field(min_length=1)
    seed_character: SeedCharacter


class LoadedCampaign(ContentModel):
    campaign: Campaign
    version: str
    adventures: dict[str, Adventure]
    scenes: dict[str, Scene]
    definitions: dict[str, Definition]
