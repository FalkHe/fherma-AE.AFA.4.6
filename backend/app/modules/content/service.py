import json
import re
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.modules.content.errors import ContentInvalidError, ContentNotFoundError
from app.modules.content.schemas import (
    Adventure,
    Campaign,
    LoadedCampaign,
    ObjectTemplate,
    Scene,
)

CONTENT_ROOT: Path = Path(__file__).resolve().parents[3] / "content"
VERSION_PATTERN: re.Pattern[str] = re.compile(r"^v[0-9]+$")

_CONTENT_ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _is_content_id(value: str) -> bool:
    return bool(_CONTENT_ID_PATTERN.match(value))


def _load_json_model(path: Path, model: type[BaseModel]) -> tuple[BaseModel | None, str | None]:
    """Read, parse and validate one JSON file against a schema.

    Returns (instance, None) on success, or (None, "[TAG] detail") on any
    read, parse or schema failure.
    """
    try:
        text = path.read_text()
    except OSError as exc:
        return None, f"[READ] {exc}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"[READ] {exc}"
    try:
        instance = model.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(part) for part in first["loc"])
        msg = first["msg"]
        detail = f"{loc}: {msg}" if loc else msg
        return None, f"[SCHEMA] {detail}"
    return instance, None


def list_campaign_ids() -> list[str]:
    campaigns_dir = CONTENT_ROOT / "campaigns"
    if not campaigns_dir.is_dir():
        return []
    return sorted(entry.name for entry in campaigns_dir.iterdir() if entry.is_dir())


def list_versions(campaign_id: str) -> list[str]:
    if not _is_content_id(campaign_id):
        raise ContentNotFoundError(f"campaigns/{campaign_id}")
    campaign_dir = CONTENT_ROOT / "campaigns" / campaign_id
    if not campaign_dir.is_dir():
        raise ContentNotFoundError(f"campaigns/{campaign_id}")
    versions = [
        entry.name
        for entry in campaign_dir.iterdir()
        if entry.is_dir() and VERSION_PATTERN.match(entry.name)
    ]
    versions.sort(key=lambda v: int(v[1:]))
    return versions


def load_campaign(campaign_id: str, version: str) -> LoadedCampaign:
    if not _is_content_id(campaign_id) or not VERSION_PATTERN.match(version):
        raise ContentNotFoundError(f"campaigns/{campaign_id}/{version}")

    base = CONTENT_ROOT / "campaigns" / campaign_id / version
    if not base.is_dir():
        raise ContentNotFoundError(f"campaigns/{campaign_id}/{version}")

    errors: list[str] = []

    campaign_path = base / "campaign.json"
    campaign, campaign_err = _load_json_model(campaign_path, Campaign)
    if campaign_err:
        raise ContentInvalidError(campaign_id, version, [f"campaign.json: {campaign_err}"])
    assert isinstance(campaign, Campaign)

    if campaign.id != campaign_id:
        errors.append(
            f"campaign.json: [R2] campaign id '{campaign.id}' does not match "
            f"directory '{campaign_id}'"
        )

    # R13: an object template id appears at most once in campaign.object_templates.
    # The first occurrence keeps the id; later ones are excluded from the result.
    templates_by_id: dict[str, ObjectTemplate] = {}
    for template in campaign.object_templates:
        if template.id in templates_by_id:
            errors.append(f"campaign.json: [R13] duplicate object template id '{template.id}'")
            continue
        templates_by_id[template.id] = template

    # R15: template name unique, case-insensitively, across all kinds.
    name_groups: dict[str, list[str]] = {}
    for template_id in sorted(templates_by_id):
        name_key = templates_by_id[template_id].name.strip().lower()
        name_groups.setdefault(name_key, []).append(template_id)
    for template_ids in name_groups.values():
        for dup_id in template_ids[1:]:
            errors.append(
                f"campaign.json: [R15] object template '{dup_id}' duplicates the name "
                f"'{templates_by_id[dup_id].name}'"
            )

    seen: set[str] = set()
    duplicate_ids: set[str] = set()
    dedup_adventure_ids: list[str] = []
    for adventure_id in campaign.adventures:
        if adventure_id in seen:
            duplicate_ids.add(adventure_id)
            continue
        seen.add(adventure_id)
        dedup_adventure_ids.append(adventure_id)
    for adventure_id in sorted(duplicate_ids):
        errors.append(
            f"campaign.json: [R4] adventure '{adventure_id}' listed more than once "
            "in campaign.adventures"
        )

    adventures_dir = base / "adventures"
    adventure_files_by_stem = {f.stem: f for f in adventures_dir.glob("*.json")}

    for stem, path in adventure_files_by_stem.items():
        if stem not in dedup_adventure_ids:
            errors.append(
                f"adventures/{path.name}: [R5] adventure not listed in campaign.adventures"
            )

    adventures_by_id: dict[str, Adventure] = {}
    for adventure_id in dedup_adventure_ids:
        path = adventure_files_by_stem.get(adventure_id)
        if path is None:
            errors.append(
                f"campaign.json: [R4] adventure '{adventure_id}' has no "
                f"adventures/{adventure_id}.json"
            )
            continue
        adventure, err = _load_json_model(path, Adventure)
        if err:
            errors.append(f"adventures/{path.name}: {err}")
            continue
        assert isinstance(adventure, Adventure)
        if adventure.id != adventure_id:
            errors.append(
                f"adventures/{path.name}: [R6] adventure id '{adventure.id}' does not "
                f"match filename '{adventure_id}'"
            )
            continue
        adventures_by_id[adventure_id] = adventure

    for adventure_id, adventure in adventures_by_id.items():
        scene_ids = [scene.id for scene in adventure.scenes]
        if adventure.entry_scene not in scene_ids:
            errors.append(
                f"adventures/{adventure_id}.json: [R7] entry_scene "
                f"'{adventure.entry_scene}' is not in this adventure's scenes"
            )

    scenes_by_id: dict[str, Scene] = {}
    scene_owner_by_id: dict[str, str] = {}
    for adventure_id in dedup_adventure_ids:
        adventure = adventures_by_id.get(adventure_id)
        if adventure is None:
            continue
        for scene in adventure.scenes:
            if scene.id in scenes_by_id:
                errors.append(
                    f"adventures/{adventure_id}.json: [R8] scene '{scene.id}' is not "
                    "unique across the campaign"
                )
                continue
            scenes_by_id[scene.id] = scene
            scene_owner_by_id[scene.id] = adventure_id

    for adventure_id, adventure in adventures_by_id.items():
        adventure_scene_ids = {scene.id for scene in adventure.scenes}
        for scene in adventure.scenes:
            if scene_owner_by_id.get(scene.id) != adventure_id:
                continue

            # R19: an exit id is unique within its own scene.
            seen_exit_ids: set[str] = set()
            for exit_ in scene.exits:
                if exit_.id in seen_exit_ids:
                    errors.append(
                        f"adventures/{adventure_id}.json: [R19] scene '{scene.id}': "
                        f"duplicate exit id '{exit_.id}'"
                    )
                    continue
                seen_exit_ids.add(exit_.id)

            # R9: a scene exit targets a different, known scene. adventure_end
            # exits carry no `to` and are exempt.
            for exit_ in scene.exits:
                if exit_.kind != "scene":
                    continue
                if exit_.to == scene.id or exit_.to not in adventure_scene_ids:
                    errors.append(
                        f"adventures/{adventure_id}.json: [R9] scene '{scene.id}': "
                        f"exit targets unknown scene '{exit_.to}'"
                    )

        reachable: set[str] = {adventure.entry_scene}
        frontier = [adventure.entry_scene]
        while frontier:
            current = frontier.pop()
            scene = scenes_by_id.get(current)
            if scene is None or scene_owner_by_id.get(current) != adventure_id:
                continue
            for exit_ in scene.exits:
                if exit_.to in adventure_scene_ids and exit_.to not in reachable:
                    reachable.add(exit_.to)
                    frontier.append(exit_.to)
        for scene in adventure.scenes:
            if scene_owner_by_id.get(scene.id) != adventure_id:
                continue
            if scene.id not in reachable:
                errors.append(
                    f"adventures/{adventure_id}.json: [R11] scene '{scene.id}' is not "
                    "reachable from entry_scene"
                )

        # R10: at least one reachable scene carries an adventure_end exit.
        # Reachability is computed above so this rule can rely on it.
        terminal = any(
            scene.id in reachable and any(exit_.kind == "adventure_end" for exit_ in scene.exits)
            for scene in adventure.scenes
            if scene_owner_by_id.get(scene.id) == adventure_id
        )
        if not terminal:
            errors.append(
                f"adventures/{adventure_id}.json: [R10] no scene reachable from "
                "entry_scene carries an adventure_end exit"
            )

    # R12, R16, R17, R18: placements and carries in the adventure files.
    referenced_template_ids: set[str] = set()
    for adventure_id, adventure in adventures_by_id.items():
        for scene in adventure.scenes:
            if scene_owner_by_id.get(scene.id) != adventure_id:
                continue
            placement_ids: set[str] = set()
            for placement in scene.placements:
                referenced_template_ids.add(placement.template)
                template = templates_by_id.get(placement.template)
                if template is None:
                    errors.append(
                        f"adventures/{adventure_id}.json: [R12] scene '{scene.id}': "
                        f"unknown object template '{placement.template}'"
                    )
                elif placement.template in placement_ids:
                    errors.append(
                        f"adventures/{adventure_id}.json: [R16] scene '{scene.id}': "
                        f"template '{placement.template}' placed more than once"
                    )
                placement_ids.add(placement.template)

                if template is not None and template.kind == "item" and placement.carries:
                    errors.append(
                        f"adventures/{adventure_id}.json: [R18] scene '{scene.id}': "
                        f"item placement '{placement.template}' cannot carry"
                    )

                carried_ids: set[str] = set()
                for carried in placement.carries:
                    referenced_template_ids.add(carried.template)
                    carried_template = templates_by_id.get(carried.template)
                    if carried_template is None:
                        errors.append(
                            f"adventures/{adventure_id}.json: [R12] scene '{scene.id}': "
                            f"unknown object template '{carried.template}'"
                        )
                    elif carried_template.kind != "item":
                        errors.append(
                            f"adventures/{adventure_id}.json: [R17] scene '{scene.id}': "
                            f"carried template '{carried.template}' is not an item"
                        )
                    elif carried.template in carried_ids:
                        errors.append(
                            f"adventures/{adventure_id}.json: [R16] scene '{scene.id}': "
                            f"template '{carried.template}' carried more than once"
                        )
                    carried_ids.add(carried.template)

    # R12, R14, R17: bypassed_by entries on fixture checks in campaign.json.
    for template_id in sorted(templates_by_id):
        template = templates_by_id[template_id]
        if template.kind != "fixture":
            continue
        for check_index, check in enumerate(template.checks):
            for entry_index, entry_id in enumerate(check.bypassed_by):
                referenced_template_ids.add(entry_id)
                entry_template = templates_by_id.get(entry_id)
                if entry_template is None:
                    errors.append(
                        f"campaign.json: [R12] fixture '{template.id}': check {check_index} "
                        f"bypassed_by entry {entry_index} names unknown object template "
                        f"'{entry_id}'"
                    )
                elif entry_template.kind != "item":
                    errors.append(
                        f"campaign.json: [R17] fixture '{template.id}': check {check_index} "
                        f"bypassed_by entry {entry_index} '{entry_id}' is not an item"
                    )

    # R20: seed character inventory entries name an item template. They also
    # count towards R14's reference set.
    for entry_index, entry_id in enumerate(campaign.seed_character.inventory):
        referenced_template_ids.add(entry_id)
        entry_template = templates_by_id.get(entry_id)
        if entry_template is None:
            errors.append(
                f"campaign.json: [R20] seed character inventory entry {entry_index} "
                f"names unknown object template '{entry_id}'"
            )
        elif entry_template.kind != "item":
            errors.append(
                f"campaign.json: [R20] seed character inventory entry {entry_index} "
                f"'{entry_id}' is not an item"
            )

    # R14: every declared template is referenced somewhere.
    for template_id in sorted(templates_by_id):
        if template_id not in referenced_template_ids:
            errors.append(
                f"campaign.json: [R14] object template '{template_id}' is not "
                "referenced by any scene"
            )

    if errors:
        raise ContentInvalidError(campaign_id, version, sorted(errors))

    return LoadedCampaign(
        campaign=campaign,
        version=version,
        adventures={aid: adventures_by_id[aid] for aid in dedup_adventure_ids},
        scenes=scenes_by_id,
        object_templates=templates_by_id,
    )


def load_scene(campaign_id: str, version: str, scene_id: str) -> Scene:
    if not _is_content_id(campaign_id) or not VERSION_PATTERN.match(version):
        raise ContentNotFoundError(f"campaigns/{campaign_id}/{version}")
    if not _is_content_id(scene_id):
        raise ContentNotFoundError(f"campaigns/{campaign_id}/{version}/scene/{scene_id}")
    loaded = load_campaign(campaign_id, version)
    if scene_id not in loaded.scenes:
        raise ContentNotFoundError(f"campaigns/{campaign_id}/{version}/scene/{scene_id}")
    return loaded.scenes[scene_id]


def load_object_template(campaign_id: str, version: str, template_id: str) -> ObjectTemplate:
    if not _is_content_id(campaign_id) or not VERSION_PATTERN.match(version):
        raise ContentNotFoundError(f"campaigns/{campaign_id}/{version}")
    if not _is_content_id(template_id):
        raise ContentNotFoundError(
            f"campaigns/{campaign_id}/{version}/object-template/{template_id}"
        )
    loaded = load_campaign(campaign_id, version)
    if template_id not in loaded.object_templates:
        raise ContentNotFoundError(
            f"campaigns/{campaign_id}/{version}/object-template/{template_id}"
        )
    return loaded.object_templates[template_id]
