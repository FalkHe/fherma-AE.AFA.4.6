---
author: architect
owner: agent
created: 2026-09-22
---
# Research: sprint 009-04

## Facts

- Draft plumbing: `CreationContext(db, user_id, run_id, ready_made)` (`agent/state.py:17`); `CreationState.draft` merges **top-level keys**, last write wins per key, so two writing tools in one model step both land (`state.py:24`, regression test `tests/character/test_creation_agent.py:205`).
- `_request_from_draft` (`agent/tools.py:37`) hard-codes `alignment="Neutral"`, `skills=[]`, `equipment_picks=[]`, `free_ability_bonuses=[]` and falls back to `builder.suggested_scores` when `abilities` is absent (`:41`). `_draft_gaps` requires race, class, name (`:30`).
- Point buy: `point_buy_cost` (`builder.py:72`), `validate_point_buy` (`:77`), budget 27, range 8–15 (`options.py:725`). `builder.build_sheet` **always** validates (`builder.py:218`) — so a rolled 7 or 16 from `roll_scores` (`:101`, 4d6-drop-lowest through `dice.roll`, seam `playthrough/dice.py:68`) raises `CharacterBuildError` today.
- Skills: `build_sheet` copies `request.skills` verbatim (`builder.py:246`); `CharacterClass.skill_choices` / `.skill_options` (`schemas.py:169`) are read **nowhere** in the builder — class auto-fill does not exist yet.
- Equipment: `resolve_equipment` defaults a missing or short pick to option 0 (`builder.py:199`); `EquipmentChoice.options[0]` is the documented default (`schemas.py:158`); labels are hand-authored and already carry "(a)"/"(b)" (`classes.py:55`). `weapon_category` picks resolve to mace / longsword (`builder.py:36`).
- AC6 needs **no** render change: `render_sheet` already prints alignment (`service.py:148`), `Skills:` (`:154`) and `Equipment:` (`:155`). Only the data is missing.
- `render_seed` prints `seed.inventory`, which is content **ids** (`service.py:175`, `content/schemas.py:137`, e.g. `shepherds-knife`); the names live on `campaign.object_templates[].name` (`content/schemas.py:39`), loaded already by `commands.py:80` (`content_service.load_campaign`).
- `CharacterCreateRequest` is also the API body of `POST …/character` (`playthrough/routes.py:108`) and is mirrored in the committed `frontend/src/api/schema.d.ts:469` — a new field there would force `make generate-api`.
- Prompt order today: identity → `suggest_scores` → `show_sheet` → save (`prompts/v1/system/creator.md:26-43`).
- Test seams: scripted model + `_tool_call` + `_invoke` (`tests/character/test_creation_agent.py:34,47,66`); `dice._rng` monkeypatch pattern (`tests/playthrough/test_service_rolls.py:254`).
- No new package and no new langgraph/langchain API: every construct used here (`@tool`, `Command`, `ToolRuntime`) is already demonstrated in `agent/tools.py` (langgraph 1.2.11 — source: local repo usage).

## Decisions (technical)

1. **Rolled scores skip point buy** via a keyword, not a wire field: `builder.build_sheet(request, *, point_buy: bool = True)` (`service.build_sheet` forwards it), called with `point_buy=not draft.get("rolled")`. Keeps `CharacterCreateRequest` and `schema.d.ts` untouched; trade-off: a web POST cannot yet submit rolled scores.
2. **Three score tools write the same draft keys** `abilities` + `rolled`. Re-rolling is calling `roll_scores` again (last write wins) — no accept flag. `set_scores` always writes, even when illegal, and its message carries `Points left: N` plus `validate_point_buy`'s problems; the model relays that text. An illegal spread still blocks `show_sheet`/`save_character` through the existing in-voice `CharacterBuildError` path (`tools.py:167`).
3. **Keep the suggested-scores fallback** (`tools.py:41`). AC1 is about what the agent *offers*; a player who never talks scores gets the class set rather than a refusal.
4. **Identity stays prompt-only** (← brief assumption): the model rewrites in tone, asks, and calls `set_identity` with the **rewritten** words after a yes; a correction is another call. `name` stays required — a looks-only correction repeats it.
5. **Class skills are auto-filled in the builder**, not in a tool: `build_sheet` sets `skills = request.skills + [s for s in cls.skill_options if s not in request.skills][:cls.skill_choices]` (story skills first, matching D14 §3). One rule, one place; no existing test asserts the old pass-through.
6. **Equipment picks live under per-choice draft keys** `equipment_pick_<i>`, not one list. The merge reducer then keeps two picks landing in one model step; one list key would drop the earlier pick. `_request_from_draft` collects `[draft.get(f"equipment_pick_{i}", 0) for i in range(len(cls.equipment))]`.
7. **"Just the default" writes nothing** — option 0 is already the default for every unset choice — so `take_default_equipment` only reports which labels were taken. Invalid state impossible by construction.
8. **`weapon_category` keeps resolving to mace/longsword** (`builder.py:36`); the prompt's plain-words hint says the tavern picks a fitting one. Naming it is D17/web work.
9. **Ready-made item names**: `CreationContext.ready_made_items: list[str] = []`, filled at CLI startup from `loaded.campaign.object_templates`; `render_seed(seed, item_names=None)` falls back to the ids (← sprint 03 backlog proposal).

## Work items

- **WI1 rules, tools, prompt** — `builder.py` (skill auto-fill, `point_buy` keyword), `service.py` (`build_sheet` keyword, `render_seed` names), `agent/tools.py` (six new tools), `prompts/v1/system/creator.md` rewritten to the step order below.
- **WI2 terminal + tests** — `commands.py` (`ready_made_items` at startup), six new scenarios in `tests/character/test_creation_agent.py` (keep the existing seven), README.

The split earns little; WI2 is the six tests and depends on WI1's signatures, fixed below.

## Interfaces

```python
# agent/tools.py — model-facing signatures only; all Command-returning tools
# write a draft delta and a ToolMessage, as the existing ones do.
roll_scores()            -> Command   # draft {"abilities": …, "rolled": True}
set_scores(strength: int, dexterity: int, constitution: int,
           intelligence: int, wisdom: int, charisma: int) -> Command
    # draft {"abilities": …, "rolled": False}; message
    # "Scores written down: STR 15, … Points left: 3." (+ "; ".join(problems))
suggest_scores()         -> Command   # unchanged, now also writes "rolled": False
set_skills(first: SkillName, second: SkillName) -> Command   # draft {"skills": [first, second]}
set_alignment(alignment: AlignmentName)         -> Command   # draft {"alignment": …}
list_equipment_choices() -> str   # reads draft class; "1. (a) a greataxe | (b) any martial melee weapon"
pick_equipment(choice_number: int, option_number: int) -> Command
    # 1-based from the listing; draft {"equipment_pick_<i>": option_index}
take_default_equipment() -> str   # labels of every still-unset choice; writes nothing
```

```python
# builder.py / service.py
def build_sheet(request: CharacterCreateRequest, *, point_buy: bool = True) -> CharacterSheet
def render_seed(seed: SeedCharacter, item_names: list[str] | None = None) -> str
# agent/state.py
CreationContext(..., ready_made_items: list[str] = [])
```

Prompt step order: ready-made offer → race/class → scores (suggested / rolled / by hand, "points left" relayed verbatim) → identity retold in tone and accepted → two story skills with a reason each → alignment with a reason → equipment one choice at a time with a plain-words hint and the default shortcut → `show_sheet` → confirm → `save_character`. D15/D16 wording untouched.

Tests (one per criterion, scripted model, `test_s04_ac…`): AC1 by-hand `set_scores` puts `Points left:` on screen and a `dice._rng`-scripted `roll_scores` puts the rolled set on the sheet; AC2 two `set_identity` calls, the second wins on the sheet; AC3 `set_skills` plus the class auto-fill both appear on the `Skills:` line; AC4 `set_alignment` appears in the header line; AC5 `pick_equipment` then `take_default_equipment` change the `Equipment:` line; AC6 one `show_sheet` output carries alignment, skills and equipment together.

## Open questions

None product-visible.
