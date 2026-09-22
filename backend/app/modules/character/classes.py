"""The twelve SRD character classes as typed literals.

Data copied from the SRD source (docs anchors given in the work item); no
loader, no I/O — this module only builds Python objects.
"""

from .schemas import (
    CharacterClass,
    EquipmentChoice,
    EquipmentOption,
    GearRef,
)

ALL_SKILLS = [
    "Acrobatics",
    "Animal Handling",
    "Arcana",
    "Athletics",
    "Deception",
    "History",
    "Insight",
    "Intimidation",
    "Investigation",
    "Medicine",
    "Nature",
    "Perception",
    "Performance",
    "Persuasion",
    "Religion",
    "Sleight of Hand",
    "Stealth",
    "Survival",
]

CLASSES: list[CharacterClass] = [
    CharacterClass(
        name="Barbarian",
        hit_die=12,
        saving_throws=["strength", "constitution"],
        skill_choices=2,
        skill_options=[
            "Animal Handling",
            "Athletics",
            "Intimidation",
            "Nature",
            "Perception",
            "Survival",
        ],
        armour_proficiencies=["light armor", "medium armor", "shields"],
        weapon_proficiencies=["simple weapons", "martial weapons"],
        equipment=[
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a greataxe",
                        items=[GearRef(kind="weapon", id="greataxe")],
                    ),
                    EquipmentOption(
                        label="(b) any martial melee weapon",
                        items=[GearRef(kind="weapon_category", id="martial_melee")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) two handaxes",
                        items=[GearRef(kind="weapon", id="handaxe", quantity=2)],
                    ),
                    EquipmentOption(
                        label="(b) any simple weapon",
                        items=[GearRef(kind="weapon_category", id="simple")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="An explorer's pack and four javelins",
                        items=[
                            GearRef(kind="pack", id="explorers-pack"),
                            GearRef(kind="weapon", id="javelin", quantity=4),
                        ],
                    ),
                ]
            ),
        ],
    ),
    CharacterClass(
        name="Bard",
        hit_die=8,
        saving_throws=["dexterity", "charisma"],
        skill_choices=3,
        skill_options=ALL_SKILLS,
        armour_proficiencies=["light armor"],
        weapon_proficiencies=[
            "simple weapons",
            "hand crossbows",
            "longswords",
            "rapiers",
            "shortswords",
        ],
        equipment=[
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a rapier",
                        items=[GearRef(kind="weapon", id="rapier")],
                    ),
                    EquipmentOption(
                        label="(b) a longsword",
                        items=[GearRef(kind="weapon", id="longsword")],
                    ),
                    EquipmentOption(
                        label="(c) any simple weapon",
                        items=[GearRef(kind="weapon_category", id="simple")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a diplomat's pack",
                        items=[GearRef(kind="pack", id="diplomats-pack")],
                    ),
                    EquipmentOption(
                        label="(b) an entertainer's pack",
                        items=[GearRef(kind="pack", id="entertainers-pack")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a lute",
                        items=[GearRef(kind="gear", id="musical-instrument")],
                    ),
                    EquipmentOption(
                        label="(b) any other musical instrument",
                        items=[GearRef(kind="gear", id="musical-instrument")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="Leather armor and a dagger",
                        items=[
                            GearRef(kind="armour", id="leather-armor"),
                            GearRef(kind="weapon", id="dagger"),
                        ],
                    ),
                ]
            ),
        ],
    ),
    CharacterClass(
        name="Cleric",
        hit_die=8,
        saving_throws=["wisdom", "charisma"],
        skill_choices=2,
        skill_options=["History", "Insight", "Medicine", "Persuasion", "Religion"],
        armour_proficiencies=["light armor", "medium armor", "shields"],
        weapon_proficiencies=["simple weapons"],
        equipment=[
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a mace",
                        items=[GearRef(kind="weapon", id="mace")],
                    ),
                    EquipmentOption(
                        label="(b) a warhammer (if proficient)",
                        items=[GearRef(kind="weapon", id="warhammer")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) scale mail",
                        items=[GearRef(kind="armour", id="scale-mail")],
                    ),
                    EquipmentOption(
                        label="(b) leather armor",
                        items=[GearRef(kind="armour", id="leather-armor")],
                    ),
                    EquipmentOption(
                        label="(c) chain mail (if proficient)",
                        items=[GearRef(kind="armour", id="chain-mail")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a light crossbow and 20 bolts",
                        items=[
                            GearRef(kind="weapon", id="light-crossbow"),
                            GearRef(kind="gear", id="crossbow-bolts", quantity=20),
                        ],
                    ),
                    EquipmentOption(
                        label="(b) any simple weapon",
                        items=[GearRef(kind="weapon_category", id="simple")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a priest's pack",
                        items=[GearRef(kind="pack", id="priests-pack")],
                    ),
                    EquipmentOption(
                        label="(b) an explorer's pack",
                        items=[GearRef(kind="pack", id="explorers-pack")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="A shield and a holy symbol",
                        items=[
                            GearRef(kind="armour", id="shield"),
                            GearRef(kind="gear", id="holy-symbol"),
                        ],
                    ),
                ]
            ),
        ],
    ),
    CharacterClass(
        name="Druid",
        hit_die=8,
        saving_throws=["intelligence", "wisdom"],
        skill_choices=2,
        skill_options=[
            "Arcana",
            "Animal Handling",
            "Insight",
            "Medicine",
            "Nature",
            "Perception",
            "Religion",
            "Survival",
        ],
        armour_proficiencies=[
            "light armor",
            "medium armor",
            "shields (druids will not wear armor or use shields made of metal)",
        ],
        weapon_proficiencies=[
            "clubs",
            "daggers",
            "darts",
            "javelins",
            "maces",
            "quarterstaffs",
            "scimitars",
            "sickles",
            "slings",
            "spears",
        ],
        equipment=[
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a wooden shield",
                        items=[GearRef(kind="armour", id="shield")],
                    ),
                    EquipmentOption(
                        label="(b) any simple weapon",
                        items=[GearRef(kind="weapon_category", id="simple")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a scimitar",
                        items=[GearRef(kind="weapon", id="scimitar")],
                    ),
                    EquipmentOption(
                        label="(b) any simple melee weapon",
                        items=[GearRef(kind="weapon_category", id="simple_melee")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="Leather armor, an explorer's pack, and a druidic focus",
                        items=[
                            GearRef(kind="armour", id="leather-armor"),
                            GearRef(kind="pack", id="explorers-pack"),
                            GearRef(kind="gear", id="druidic-focus"),
                        ],
                    ),
                ]
            ),
        ],
    ),
    CharacterClass(
        name="Fighter",
        hit_die=10,
        saving_throws=["strength", "constitution"],
        skill_choices=2,
        skill_options=[
            "Acrobatics",
            "Animal Handling",
            "Athletics",
            "History",
            "Insight",
            "Intimidation",
            "Perception",
            "Survival",
        ],
        armour_proficiencies=["all armor", "shields"],
        weapon_proficiencies=["simple weapons", "martial weapons"],
        equipment=[
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) chain mail",
                        items=[GearRef(kind="armour", id="chain-mail")],
                    ),
                    EquipmentOption(
                        label="(b) leather armor, longbow, and 20 arrows",
                        items=[
                            GearRef(kind="armour", id="leather-armor"),
                            GearRef(kind="weapon", id="longbow"),
                            GearRef(kind="gear", id="arrows", quantity=20),
                        ],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a martial weapon and a shield",
                        items=[
                            GearRef(kind="weapon_category", id="martial"),
                            GearRef(kind="armour", id="shield"),
                        ],
                    ),
                    EquipmentOption(
                        label="(b) two martial weapons",
                        items=[GearRef(kind="weapon_category", id="martial", quantity=2)],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a light crossbow and 20 bolts",
                        items=[
                            GearRef(kind="weapon", id="light-crossbow"),
                            GearRef(kind="gear", id="crossbow-bolts", quantity=20),
                        ],
                    ),
                    EquipmentOption(
                        label="(b) two handaxes",
                        items=[GearRef(kind="weapon", id="handaxe", quantity=2)],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a dungeoneer's pack",
                        items=[GearRef(kind="pack", id="dungeoneers-pack")],
                    ),
                    EquipmentOption(
                        label="(b) an explorer's pack",
                        items=[GearRef(kind="pack", id="explorers-pack")],
                    ),
                ]
            ),
        ],
    ),
    CharacterClass(
        name="Monk",
        hit_die=8,
        saving_throws=["strength", "dexterity"],
        skill_choices=2,
        skill_options=["Acrobatics", "Athletics", "History", "Insight", "Religion", "Stealth"],
        armour_proficiencies=["none"],
        weapon_proficiencies=["simple weapons", "shortswords"],
        equipment=[
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a shortsword",
                        items=[GearRef(kind="weapon", id="shortsword")],
                    ),
                    EquipmentOption(
                        label="(b) any simple weapon",
                        items=[GearRef(kind="weapon_category", id="simple")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a dungeoneer's pack",
                        items=[GearRef(kind="pack", id="dungeoneers-pack")],
                    ),
                    EquipmentOption(
                        label="(b) an explorer's pack",
                        items=[GearRef(kind="pack", id="explorers-pack")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="10 darts",
                        items=[GearRef(kind="weapon", id="dart", quantity=10)],
                    ),
                ]
            ),
        ],
    ),
    CharacterClass(
        name="Paladin",
        hit_die=10,
        saving_throws=["wisdom", "charisma"],
        skill_choices=2,
        skill_options=[
            "Athletics",
            "Insight",
            "Intimidation",
            "Medicine",
            "Persuasion",
            "Religion",
        ],
        armour_proficiencies=["all armor", "shields"],
        weapon_proficiencies=["simple weapons", "martial weapons"],
        equipment=[
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a martial weapon and a shield",
                        items=[
                            GearRef(kind="weapon_category", id="martial"),
                            GearRef(kind="armour", id="shield"),
                        ],
                    ),
                    EquipmentOption(
                        label="(b) two martial weapons",
                        items=[GearRef(kind="weapon_category", id="martial", quantity=2)],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) five javelins",
                        items=[GearRef(kind="weapon", id="javelin", quantity=5)],
                    ),
                    EquipmentOption(
                        label="(b) any simple melee weapon",
                        items=[GearRef(kind="weapon_category", id="simple_melee")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a priest's pack",
                        items=[GearRef(kind="pack", id="priests-pack")],
                    ),
                    EquipmentOption(
                        label="(b) an explorer's pack",
                        items=[GearRef(kind="pack", id="explorers-pack")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="Chain mail and a holy symbol",
                        items=[
                            GearRef(kind="armour", id="chain-mail"),
                            GearRef(kind="gear", id="holy-symbol"),
                        ],
                    ),
                ]
            ),
        ],
    ),
    CharacterClass(
        name="Ranger",
        hit_die=10,
        saving_throws=["strength", "dexterity"],
        skill_choices=3,
        skill_options=[
            "Animal Handling",
            "Athletics",
            "Insight",
            "Investigation",
            "Nature",
            "Perception",
            "Stealth",
            "Survival",
        ],
        armour_proficiencies=["light armor", "medium armor", "shields"],
        weapon_proficiencies=["simple weapons", "martial weapons"],
        equipment=[
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) scale mail",
                        items=[GearRef(kind="armour", id="scale-mail")],
                    ),
                    EquipmentOption(
                        label="(b) leather armor",
                        items=[GearRef(kind="armour", id="leather-armor")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) two shortswords",
                        items=[GearRef(kind="weapon", id="shortsword", quantity=2)],
                    ),
                    EquipmentOption(
                        label="(b) two simple melee weapons",
                        items=[GearRef(kind="weapon_category", id="simple_melee", quantity=2)],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a dungeoneer's pack",
                        items=[GearRef(kind="pack", id="dungeoneers-pack")],
                    ),
                    EquipmentOption(
                        label="(b) an explorer's pack",
                        items=[GearRef(kind="pack", id="explorers-pack")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="A longbow and a quiver of 20 arrows",
                        items=[
                            GearRef(kind="weapon", id="longbow"),
                            GearRef(kind="gear", id="arrows", quantity=20),
                        ],
                    ),
                ]
            ),
        ],
    ),
    CharacterClass(
        name="Rogue",
        hit_die=8,
        saving_throws=["dexterity", "intelligence"],
        skill_choices=4,
        skill_options=[
            "Acrobatics",
            "Athletics",
            "Deception",
            "Insight",
            "Intimidation",
            "Investigation",
            "Perception",
            "Performance",
            "Persuasion",
            "Sleight of Hand",
            "Stealth",
        ],
        armour_proficiencies=["light armor"],
        weapon_proficiencies=[
            "simple weapons",
            "hand crossbows",
            "longswords",
            "rapiers",
            "shortswords",
        ],
        equipment=[
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a rapier",
                        items=[GearRef(kind="weapon", id="rapier")],
                    ),
                    EquipmentOption(
                        label="(b) a shortsword",
                        items=[GearRef(kind="weapon", id="shortsword")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a shortbow and quiver of 20 arrows",
                        items=[
                            GearRef(kind="weapon", id="shortbow"),
                            GearRef(kind="gear", id="arrows", quantity=20),
                        ],
                    ),
                    EquipmentOption(
                        label="(b) a shortsword",
                        items=[GearRef(kind="weapon", id="shortsword")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a burglar's pack",
                        items=[GearRef(kind="pack", id="burglars-pack")],
                    ),
                    EquipmentOption(
                        label="(b) a dungeoneer's pack",
                        items=[GearRef(kind="pack", id="dungeoneers-pack")],
                    ),
                    EquipmentOption(
                        label="(c) an explorer's pack",
                        items=[GearRef(kind="pack", id="explorers-pack")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) Leather armor, two daggers, and thieves' tools",
                        items=[
                            GearRef(kind="armour", id="leather-armor"),
                            GearRef(kind="weapon", id="dagger", quantity=2),
                            GearRef(kind="gear", id="thieves-tools"),
                        ],
                    ),
                ]
            ),
        ],
    ),
    CharacterClass(
        name="Sorcerer",
        hit_die=6,
        saving_throws=["constitution", "charisma"],
        skill_choices=2,
        skill_options=["Arcana", "Deception", "Insight", "Intimidation", "Persuasion", "Religion"],
        armour_proficiencies=["none"],
        weapon_proficiencies=["daggers", "darts", "slings", "quarterstaffs", "light crossbows"],
        equipment=[
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a light crossbow and 20 bolts",
                        items=[
                            GearRef(kind="weapon", id="light-crossbow"),
                            GearRef(kind="gear", id="crossbow-bolts", quantity=20),
                        ],
                    ),
                    EquipmentOption(
                        label="(b) any simple weapon",
                        items=[GearRef(kind="weapon_category", id="simple")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a component pouch",
                        items=[GearRef(kind="gear", id="component-pouch")],
                    ),
                    EquipmentOption(
                        label="(b) an arcane focus",
                        items=[GearRef(kind="gear", id="arcane-focus")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a dungeoneer's pack",
                        items=[GearRef(kind="pack", id="dungeoneers-pack")],
                    ),
                    EquipmentOption(
                        label="(b) an explorer's pack",
                        items=[GearRef(kind="pack", id="explorers-pack")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="Two daggers",
                        items=[GearRef(kind="weapon", id="dagger", quantity=2)],
                    ),
                ]
            ),
        ],
    ),
    CharacterClass(
        name="Warlock",
        hit_die=8,
        saving_throws=["wisdom", "charisma"],
        skill_choices=2,
        skill_options=[
            "Arcana",
            "Deception",
            "History",
            "Intimidation",
            "Investigation",
            "Nature",
            "Religion",
        ],
        armour_proficiencies=["light armor"],
        weapon_proficiencies=["simple weapons"],
        equipment=[
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a light crossbow and 20 bolts",
                        items=[
                            GearRef(kind="weapon", id="light-crossbow"),
                            GearRef(kind="gear", id="crossbow-bolts", quantity=20),
                        ],
                    ),
                    EquipmentOption(
                        label="(b) any simple weapon",
                        items=[GearRef(kind="weapon_category", id="simple")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a component pouch",
                        items=[GearRef(kind="gear", id="component-pouch")],
                    ),
                    EquipmentOption(
                        label="(b) an arcane focus",
                        items=[GearRef(kind="gear", id="arcane-focus")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a scholar's pack",
                        items=[GearRef(kind="pack", id="scholars-pack")],
                    ),
                    EquipmentOption(
                        label="(b) a dungeoneer's pack",
                        items=[GearRef(kind="pack", id="dungeoneers-pack")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="Leather armor, any simple weapon, and two daggers",
                        items=[
                            GearRef(kind="armour", id="leather-armor"),
                            GearRef(kind="weapon_category", id="simple"),
                            GearRef(kind="weapon", id="dagger", quantity=2),
                        ],
                    ),
                ]
            ),
        ],
    ),
    CharacterClass(
        name="Wizard",
        hit_die=6,
        saving_throws=["intelligence", "wisdom"],
        skill_choices=2,
        skill_options=["Arcana", "History", "Insight", "Investigation", "Medicine", "Religion"],
        armour_proficiencies=["none"],
        weapon_proficiencies=["daggers", "darts", "slings", "quarterstaffs", "light crossbows"],
        equipment=[
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a quarterstaff",
                        items=[GearRef(kind="weapon", id="quarterstaff")],
                    ),
                    EquipmentOption(
                        label="(b) a dagger",
                        items=[GearRef(kind="weapon", id="dagger")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a component pouch",
                        items=[GearRef(kind="gear", id="component-pouch")],
                    ),
                    EquipmentOption(
                        label="(b) an arcane focus",
                        items=[GearRef(kind="gear", id="arcane-focus")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="(a) a scholar's pack",
                        items=[GearRef(kind="pack", id="scholars-pack")],
                    ),
                    EquipmentOption(
                        label="(b) an explorer's pack",
                        items=[GearRef(kind="pack", id="explorers-pack")],
                    ),
                ]
            ),
            EquipmentChoice(
                options=[
                    EquipmentOption(
                        label="A spellbook",
                        items=[GearRef(kind="gear", id="spellbook")],
                    ),
                ]
            ),
        ],
    ),
]
