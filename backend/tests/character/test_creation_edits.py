"""Draft edits and tool prerequisites visible to character creation players."""

from types import SimpleNamespace

from app.modules.character import service
from app.modules.character.agent import state, tools


def _runtime(draft):
    return SimpleNamespace(state={"draft": draft}, tool_call_id="test-call")


def test_equipment_without_a_recorded_class_explains_the_next_step():
    refusal = tools.list_equipment_choices.func(runtime=_runtime({"name": "Rosalind"}))
    message = refusal.update["messages"][0].content

    assert "class" in message
    assert "confirm" in message
    assert "tavern is noisy" not in message
    assert refusal.update["messages"][0].additional_kwargs["show_player"] is True


def test_changes_are_reflected_in_the_partial_preview():
    draft = {"race": "Human", "character_class": "Fighter"}
    draft = state._merge_draft(  # noqa: SLF001 - exercise the graph's draft reducer
        draft, tools.set_identity.func(name="Ada", runtime=_runtime(draft)).update["draft"]
    )
    draft = state._merge_draft(  # noqa: SLF001
        draft,
        tools.set_skills.func(first="Athletics", second="Survival", runtime=_runtime(draft)).update[
            "draft"
        ],
    )
    draft = state._merge_draft(  # noqa: SLF001
        draft,
        tools.pick_equipment.func(choice_number=1, option_number=1, runtime=_runtime(draft)).update[
            "draft"
        ],
    )
    preview = service.creation_progress(draft)
    assert preview.sheet.name == "Ada"
    assert "Athletics" in preview.sheet.skills
    assert "Survival" in preview.sheet.skills
    assert "Chain Mail" in preview.sheet.equipment
    assert preview.step == "scores"
    assert preview.can_save is False

    draft = state._merge_draft(  # noqa: SLF001
        draft, tools.set_identity.func(name="Bea", runtime=_runtime(draft)).update["draft"]
    )
    assert service.creation_progress(draft).sheet.name == "Bea"


def test_changing_class_clears_old_equipment_choices():
    draft = {
        "race": "Human",
        "character_class": "Fighter",
        "equipment_pick_0": 1,
        "equipment_defaults": True,
    }
    change = tools.set_race_and_class.func(
        race="Human", character_class="Rogue", runtime=_runtime(draft)
    )
    updated = state._merge_draft(draft, change.update["draft"])  # noqa: SLF001

    assert updated["character_class"] == "Rogue"
    assert "equipment_pick_0" not in updated
    assert "equipment_defaults" not in updated
    assert service.creation_progress(updated).sheet.character_class == "Rogue"
    assert service.creation_progress(updated).sheet.equipment == []


def test_ready_made_edit_explains_why_it_cannot_be_written():
    result = tools.set_identity.func(name="Bea", runtime=_runtime({"ready_made": True}))

    message = result.update["messages"][0].content
    assert "ready-made hero" in message
    assert "choose a race and class" in message


def test_partial_corrections_keep_other_fields_and_show_the_first_skill():
    draft = {"race": "Human", "character_class": "Fighter", "name": "Ada"}
    class_change = tools.set_race_and_class.func(character_class="Rogue", runtime=_runtime(draft))
    draft = state._merge_draft(draft, class_change.update["draft"])  # noqa: SLF001
    assert draft["race"] == "Human"
    assert draft["character_class"] == "Rogue"

    looks_change = tools.set_identity.func(appearance="A green cloak", runtime=_runtime(draft))
    draft = state._merge_draft(draft, looks_change.update["draft"])  # noqa: SLF001
    assert draft["name"] == "Ada"
    assert service.creation_progress(draft).sheet.appearance == "A green cloak"

    first_skill = tools.set_skills.func(first="Stealth", runtime=_runtime(draft))
    draft = state._merge_draft(draft, first_skill.update["draft"])  # noqa: SLF001
    assert draft["skills"] == ["Stealth"]
    assert "Stealth" in service.creation_progress(draft).sheet.skills
    assert service.creation_progress(draft).step == "scores"

    second_skill = tools.set_skills.func(second="Deception", runtime=_runtime(draft))
    draft = state._merge_draft(draft, second_skill.update["draft"])  # noqa: SLF001
    assert draft["skills"] == ["Stealth", "Deception"]
