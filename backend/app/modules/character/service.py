"""Read-only lookups over the SRD options and class data hand-authored as
Python literals in `options.py` (WI1: `RACES`, `SKILLS`, `ALIGNMENTS`,
`ARMOURS`, `WEAPONS`, `GEAR`, `POINT_BUY`) and `classes.py` (WI2: `CLASSES`).

A module of functions, per `AGENTS.md`'s "services are modules of
functions" rule -- callers do `from . import service`, never `from .service
import races`. Pure: no session, no I/O; every function takes no argument
except the two by-name lookups. The lookup dicts are built once at import
time from the literals above."""

from app.modules.character.classes import CLASSES
from app.modules.character.options import (
    ALIGNMENTS,
    ARMOURS,
    GEAR,
    POINT_BUY,
    RACES,
    SKILLS,
    WEAPONS,
)
from app.modules.character.schemas import (
    Alignment,
    Armour,
    CharacterClass,
    CharacterCreateRequest,
    CharacterSheet,
    ClassName,
    GearItem,
    PointBuy,
    Race,
    RaceName,
    Skill,
    Weapon,
)

_RACES_BY_NAME: dict[RaceName, Race] = {race.name: race for race in RACES}
_CLASSES_BY_NAME: dict[ClassName, CharacterClass] = {cls.name: cls for cls in CLASSES}


def races() -> list[Race]:
    return RACES


def classes() -> list[CharacterClass]:
    return CLASSES


def skills() -> list[Skill]:
    return SKILLS


def alignments() -> list[Alignment]:
    return ALIGNMENTS


def armours() -> list[Armour]:
    return ARMOURS


def weapons() -> list[Weapon]:
    return WEAPONS


def gear() -> list[GearItem]:
    return GEAR


def point_buy() -> PointBuy:
    return POINT_BUY


def race(name: RaceName) -> Race:
    return _RACES_BY_NAME[name]


def character_class(name: ClassName) -> CharacterClass:
    return _CLASSES_BY_NAME[name]


def build_sheet(request: CharacterCreateRequest) -> CharacterSheet:
    # Function-local: `builder` imports this module for its own lookups
    # (`race`, `character_class`), so a module-scope import here would be
    # a cycle.
    from app.modules.character import builder

    return builder.build_sheet(request)
