# character

Owns the level-1 character sheet and the SRD 5.1 options a player picks it
from — races, classes, skills, alignments, armours, weapons and gear. All of
it is hand-authored Python data (no table, no migration, level 1 only), the
same "content lives in git" approach as the `content` module.

## Owns

- The sheet shape, `CharacterSheet` (`schemas.py`, owned by WI1): name,
  race, class, alignment, ability scores, derived combat stats, saving
  throws, chosen skills, equipment, appearance and backstory.
- The SRD option data (`options.py`, WI1 / `classes.py`, WI2): `RACES`,
  `SKILLS`, `ALIGNMENTS`, `ARMOURS`, `WEAPONS`, `GEAR`, `CLASSES`.
- `POINT_BUY` (`options.py`): ability-score point-buy costs (8 → 0 … 15 →
  9), budget 27, range 8–15. This is our own house rule for turning six
  chosen scores into a balanced set — the SRD does not define point buy at
  all, it only lists the standard array and rolled stats as alternatives.

## Surface

- `service.races()` / `classes()` / `skills()` / `alignments()` /
  `armours()` / `weapons()` / `gear()` — every SRD option list, read-only,
  no argument.
- `service.point_buy()` — the point-buy rule above.
- `service.race(name)` / `service.character_class(name)` — a single option
  by name, looked up from a dict built once at import time.
- `app character options` (`commands.py`) — prints every race and class
  with its key stats to stdout, for a quick look at the option set without
  starting the API.
