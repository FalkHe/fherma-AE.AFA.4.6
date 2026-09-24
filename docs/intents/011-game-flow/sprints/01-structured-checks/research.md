---
author: fhit:architect
owner: agent
created: 2026-09-24
---
# Research: sprint 011/01 — structured checks

## Facts

Content schema (`backend/app/modules/content/schemas.py`):
- `FixtureCheck` 57-62: `action: ProseText`, `dc: int 5..30`, `success: ProseText`, `bypassed_by: list[ContentId]`. No ability field.
- `Secret` 76-79: `fact: ProseText`, `dc: int 5..30`, `discovered_by: ProseText`. No ability field.
- `Abilities` 16-22 is the canonical six-name set; `dice.derive_formula` already validates against `Abilities.model_fields` (`playthrough/dice.py:225`).
- `ContentModel` 9-10 is `extra="forbid", frozen=True`, so adding required fields rejects old files immediately — that is the whole of AC1/AC2 enforcement; no extra validator rule is needed for presence.

Where DC and ability enter resolution (`backend/app/modules/playthrough/service.py`):
- `passive_check` 1504-1543: takes `ability: str`, `dc: int` from the caller, reads `dice._actor_abilities`, `10 + modifier >= dc`.
- `_resolve_roll_outcome` 1692-1765 with `resolve_check` 1766 / `resolve_save` 1783: take `roll_id` and `dc` from the caller; the ability is already baked into the roll's formula.
- `request_player_roll` 1312-1370: `kind` + free-form `context`; the ability travels in `context["ability"]` and is consumed by `dice.derive_formula` (`dice.py:217-232`).
- So every ability and every DC is supplied by the model through `game/agent/tools.py` (`roll_dice` 173-232 `ability`/`skill`/`dc` fields, `resolve_check` 288, `resolve_save` 308, `passive_check` 328, `request_player_roll` 514-560), instructed by `backend/app/modules/game/prompts/v1/system/dm.md:8-20`.

Prose parsed for mechanics:
- **No runtime regex reads `discovered_by` or a check's `action`** — the only occurrences of `discovered_by` in backend code are the schema field (`schemas.py:78`) and test/content data. The regexes in `playthrough/dice.py:45` (dice expression) and `game/agent/nodes.py:31-80` (prompt-injection guard) are not mechanics-from-prose.
- The real prose path is the model: it reads `discovered_by`/`action` in the situation text and invents the ability, skill and DC it passes to the tools above. That is what the structured fields replace; the change is complete once resolution can be handed an authored `ability`/`skill`/`dc` instead.

Validator and its tests:
- `content.service.load_campaign` (`content/service.py:76-350`) collects `[Rn]`-tagged errors; CLI `app content validate` (`content/commands.py:9-40`) walks every campaign/version. Highest existing rule is R20 (`service.py:327`, `docs/modules/content.md:400`).
- Tests: `backend/tests/content/test_schemas.py:164-190` (DC bounds on both models), `test_shipped_tree.py:141-188` (fixture checks in the shipped tree), `test_acceptance_content_speaks_mechanics.py`, and the shared factories `backend/tests/content/conftest.py:136`. Also `backend/tests/playthrough/test_acceptance_rolls_derived_and_recorded.py:443-450` constructs `FixtureCheck`/`Secret` directly. All five construct-sites must gain the new fields.

Greenhollow entries to update — **6 total**, none ambiguous:
- `adventures/goblins-of-greenhollow.json:55` (scene `thornway`, dc 5) → wisdom / perception; `:85` (scene `lair-maw`, dc 14) → wisdom / perception. Both prose strings say "a Wisdom (Perception) check".
- `campaign.json` fixture `thorn-screen`: "Lift the lashed brush aside…" dc 13 → dexterity / null; "Cut through the lashings…" dc 10 → strength / null.
- `campaign.json` fixture `wool-sack`: "Work the knotted neck loose by hand" dc 8 → dexterity / sleight-of-hand is a stretch → dexterity / null; "Split the sack open with a heavy blade" dc 12 → strength / null.
Fixture abilities are not named in prose but follow unambiguously from the verb; recorded as assumption, not an open question.

`ability_modifier` (`dice.py:104`) applies no proficiency bonus, and nothing consumes a skill name today. Keeping `skill` data-only preserves AC4 (no number changes).

## Work items

- **WI1 — content (schema, docs, data, validator surface).** Add `ability` (required, constrained to the six `Abilities` names) and `skill: str | None = None` to `Secret` and `FixtureCheck`; fill the 6 Greenhollow entries above; update `docs/modules/content.md:182-213` §5.5/§5.6 tables and the §12 example; update the five test construct-sites so the suite still builds valid content. Add one test per model that a missing `ability` is refused and one that `app content validate` fails on a tree missing it. No new `[Rn]` rule — the model's `extra`/required validation already produces the refusal.
- **WI2 — resolution reads the authored fields.** Add an optional `skill: str | None = None` parameter to `passive_check`, and give `resolve_check`/`resolve_save` and `request_player_roll` nothing new; instead add one thin playthrough helper that turns an authored `Secret`/`FixtureCheck` into the `(ability, skill, dc)` triple the existing entry points already accept, and record `skill` on the `passive_check` tool_call args. Keep every current signature intact (AC4). Tests: derived active check, passive check and save built from an authored entry assert the authored ability reaches `dice.derive_formula` and that no prose is read.

WI1 and WI2 can run in parallel once the field names below are fixed; WI2's test fixtures construct the new models itself.

## Interfaces

```python
# content/schemas.py — both models gain exactly these two fields
AbilityName = Literal[
    "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"
]

class FixtureCheck(ContentModel):
    action: ProseText
    ability: AbilityName          # required, no default
    skill: ProseText | None = None
    dc: int = Field(ge=5, le=30)
    success: ProseText
    bypassed_by: list[ContentId] = Field(default_factory=list)

class Secret(ContentModel):
    fact: ProseText
    ability: AbilityName          # required, no default
    skill: ProseText | None = None
    dc: int = Field(ge=5, le=30)
    discovered_by: ProseText      # unchanged, narration guidance only
```

JSON keys are snake_case, matching every other content field (`ContentModel` has no alias generator).

Signatures WI2 relies on, all unchanged:

```python
dice.derive_formula(kind, actor, context, *, campaign_id, version, item=None) -> str
    # context = {"ability": <AbilityName>} for ability_check / saving_throw
service.passive_check(db, *, user_id, actor_id, ability, dc, turn_id=None, skill=None) -> bool
service.resolve_check(db, *, user_id, roll_id, dc, turn_id=None) -> bool
service.resolve_save(db, *, user_id, roll_id, dc, turn_id=None) -> bool
service.request_player_roll(db, *, user_id, actor_id, kind, context, turn_id=None) -> Event
```

Trade-off: required fields break any content file not edited in this change — acceptable, the only tree is Greenhollow plus test fixtures, and no migration exists. Failure behaviour: an unfilled entry fails `app content validate` and campaign load, loudly, at startup of a run. Blast radius: `content/schemas.py`, the two Greenhollow files, five test construct-sites, one doc section.

## Open questions

None product-visible. Fixture ability choices are recorded as assumptions in `brief.md`.
