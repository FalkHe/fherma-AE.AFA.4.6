"""Unmocked tests over the real, shipped `backend/content/` tree.

These are the step-1.3 tests (phase contract §8, P1-D13): they never
monkeypatch `service.CONTENT_ROOT`, and they never write into
`backend/content/`. They read the actual `greenhollow/v1` campaign authored
in step 1.3 and prove it loads through the real service surface.

Criterion numbers refer to `step-1.3.md` §6 ("The suite", 15-19).
"""

from typer.testing import CliRunner

from app.modules.content import service
from app.modules.content.commands import content_app

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"

runner = CliRunner()


def test_list_campaign_ids_and_versions_c15():
    assert service.list_campaign_ids() == [CAMPAIGN_ID]
    assert service.list_versions(CAMPAIGN_ID) == [VERSION]


def test_load_campaign_does_not_raise_c16():
    service.load_campaign(CAMPAIGN_ID, VERSION)


def test_loaded_campaign_structural_facts_c17():
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)

    # criterion 7: some definition placed in >= 2 different scenes
    placements_by_definition: dict[str, int] = {}
    for scene in loaded.scenes.values():
        seen_in_this_scene = {p.definition for p in scene.creatures}
        for definition_id in seen_in_this_scene:
            placements_by_definition[definition_id] = (
                placements_by_definition.get(definition_id, 0) + 1
            )
    assert any(count >= 2 for count in placements_by_definition.values())

    # criterion 8: at least one non-combatant, at least one combatant
    attack_lists = [d.stat_block.attacks for d in loaded.definitions.values()]
    assert any(attacks == [] for attacks in attack_lists)
    assert any(len(attacks) > 0 for attacks in attack_lists)

    # criterion 9: >= 2 hidden entries across >= 2 scenes, each dc in 1..30
    # and non-empty discovered_by
    scenes_with_hidden = [scene for scene in loaded.scenes.values() if scene.hidden]
    total_hidden = sum(len(scene.hidden) for scene in scenes_with_hidden)
    assert total_hidden >= 2
    assert len(scenes_with_hidden) >= 2
    for scene in scenes_with_hidden:
        for secret in scene.hidden:
            assert 1 <= secret.dc <= 30
            assert secret.discovered_by != ""

    # criterion 10 (structural half): at least one conditioned, one
    # unconditioned exit
    all_exits = [exit_ for scene in loaded.scenes.values() for exit_ in scene.exits]
    assert any(exit_.condition is not None for exit_ in all_exits)
    assert any(exit_.condition is None for exit_ in all_exits)

    # criterion 11: some creatures placement with count > 1
    all_placements = [p for scene in loaded.scenes.values() for p in scene.creatures]
    assert any(p.count > 1 for p in all_placements)

    # brief-level structural facts
    assert len(loaded.adventures) == 1
    assert len(loaded.scenes) >= 3


def test_load_scene_and_definition_from_loaded_ids_c18():
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)
    adventure = next(iter(loaded.adventures.values()))

    entry_scene_id = adventure.entry_scene
    scene = service.load_scene(CAMPAIGN_ID, VERSION, entry_scene_id)
    assert scene.id == entry_scene_id

    # a definition id taken from a placement, not hardcoded
    placement = next(p for s in loaded.scenes.values() for p in s.creatures if s.creatures)
    definition = service.load_definition(CAMPAIGN_ID, VERSION, placement.definition)
    assert definition.id == placement.definition


def test_content_app_validates_shipped_tree_c19():
    result = runner.invoke(content_app, [])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"{CAMPAIGN_ID}/{VERSION}: ok"
    assert result.stderr == ""
