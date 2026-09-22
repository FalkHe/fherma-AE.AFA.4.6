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
- `app character create --run <id> --user <id>` (`commands.py`, sprint
  009-03/04) — the terminal creation chat: prints the greeting, then loops
  turns through `service.build_creation_agent()`/`service.turn()` until
  the player quits or a save lands. `show_sheet` — draft or, for the
  ready-made hero, `show_sheet(ready_made=True)` (its equipment printed by
  name, from the campaign's own object templates, loaded once at startup)
  — always prints the full sheet itself ahead of the agent's own words,
  before the save is ever asked for; the agent never restates its
  numbers. A turn that raises (model, tool or graph) prints the same
  in-voice line as a refusal and keeps the session running, never a
  traceback. No Postgres checkpointer — the thread, and any unsaved
  draft, dies with the process.
- `POST /api/v1/character/runs/{runId}/creation` (sprint 009-05) — starts
  a creation conversation for a run: 201 with the deterministic greeting,
  409 `CHARACTER_EXISTS` if the caller already has one. `POST
  /api/v1/character/creation/{conversationId}/messages` — sends one
  player message, answers `CreationReply` (the reply, the sheet so far,
  the step reached 1-7, `canSave`, `saved`, `error`). Both routes keep
  their state only on `app.state` — one lazily built agent and a dict of
  live conversations, nothing persisted (a restart starts over, ← D12).
  `character/service.creation_progress(draft)` renders the sheet-so-far
  and the step purely from the draft; a turn that raises answers 200 with
  the in-voice `MODEL_ERROR_REPLY` line and `error: true` rather than a
  raw failure.
- The chat (sprint 009-04) walks: ready-made offer → race/class (a yes
  before writing) → ability scores, offered three ways — "suggest a set
  for my class" (`suggest_scores`), "roll for me" (`roll_scores`, the
  dice seam, re-rollable) or "I'll spend the points myself" (`set_scores`,
  27 points across six scores 8–15, the tool's own "Points left" message
  relayed verbatim after every change) → name/looks/story in any order,
  read back in tone and written down with `set_identity` only after a yes
  → two story skills (`set_skills`, class skills auto-filled) → one of
  the nine alignments (`set_alignment`) → equipment, walked one choice at
  a time (`list_equipment_choices`/`pick_equipment`), with "just the
  default" (`take_default_equipment`) taking every remaining default in
  one turn → `show_sheet` → a save confirmation.
- `service.build_sheet(request, *, point_buy=True)` (`builder.py`) —
  turns a `CharacterCreateRequest` into a finished `CharacterSheet`:
  validates the point-buy spread (skipped when `point_buy=False`, for
  scores the game rolled), applies the race, auto-fills the class's own
  skill proficiencies (SRD order, story skills first) and derives hit
  points, armour class, saving throws and each weapon's to-hit/damage
  rather than accepting any of them from the caller. Raises
  `CharacterBuildError` on an illegal spread or an unknown equipment pick.
  Starting gear is always proficient by definition — the SRD's prose
  proficiency lists are never parsed. `roll_scores()` rolls through
  `playthrough.dice`, never a caller-supplied number.
