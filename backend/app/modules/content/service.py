import json
import re
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.modules.content.errors import ContentInvalidError, ContentNotFoundError
from app.modules.content.schemas import (
    Adventure,
    Campaign,
    Definition,
    LoadedCampaign,
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
            for exit_ in scene.exits:
                if exit_.to == scene.id or exit_.to not in adventure_scene_ids:
                    errors.append(
                        f"adventures/{adventure_id}.json: [R9] scene '{scene.id}': "
                        f"exit targets unknown scene '{exit_.to}'"
                    )

        terminal = any(
            scene.exits == []
            for scene in adventure.scenes
            if scene_owner_by_id.get(scene.id) == adventure_id
        )
        if not terminal:
            errors.append(
                f"adventures/{adventure_id}.json: [R10] no scene in this adventure "
                "is terminal (exits == [])"
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

    definitions_dir = base / "definitions"
    definition_files_by_stem = {f.stem: f for f in definitions_dir.glob("*.json")}

    referenced_definition_ids: set[str] = set()
    for adventure_id, adventure in adventures_by_id.items():
        for scene in adventure.scenes:
            if scene_owner_by_id.get(scene.id) != adventure_id:
                continue
            placement_ids: set[str] = set()
            for placement in scene.creatures:
                referenced_definition_ids.add(placement.definition)
                if placement.definition not in definition_files_by_stem:
                    errors.append(
                        f"adventures/{adventure_id}.json: [R12] scene '{scene.id}': "
                        f"creature definition '{placement.definition}' not found"
                    )
                if placement.definition in placement_ids:
                    errors.append(
                        f"adventures/{adventure_id}.json: [R16] scene '{scene.id}': "
                        f"definition '{placement.definition}' placed more than once"
                    )
                placement_ids.add(placement.definition)

    definitions_by_id: dict[str, Definition] = {}
    for stem, path in definition_files_by_stem.items():
        if stem not in referenced_definition_ids:
            errors.append(f"definitions/{path.name}: [R14] definition not referenced by any scene")
            continue
        definition, err = _load_json_model(path, Definition)
        if err:
            errors.append(f"definitions/{path.name}: {err}")
            continue
        assert isinstance(definition, Definition)
        definitions_by_id[stem] = definition

    for stem, definition in definitions_by_id.items():
        if definition.id != stem:
            errors.append(
                f"definitions/{stem}.json: [R13] definition id '{definition.id}' "
                f"does not match filename '{stem}'"
            )

    name_groups: dict[str, list[str]] = {}
    for stem in sorted(definitions_by_id):
        name_key = definitions_by_id[stem].name.strip().lower()
        name_groups.setdefault(name_key, []).append(stem)
    for stems in name_groups.values():
        for dup_stem in stems[1:]:
            errors.append(
                f"definitions/{dup_stem}.json: [R15] duplicate definition name "
                f"'{definitions_by_id[dup_stem].name}'"
            )

    if errors:
        raise ContentInvalidError(campaign_id, version, sorted(errors))

    return LoadedCampaign(
        campaign=campaign,
        version=version,
        adventures={aid: adventures_by_id[aid] for aid in dedup_adventure_ids},
        scenes=scenes_by_id,
        definitions=definitions_by_id,
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


def load_definition(campaign_id: str, version: str, definition_id: str) -> Definition:
    if not _is_content_id(campaign_id) or not VERSION_PATTERN.match(version):
        raise ContentNotFoundError(f"campaigns/{campaign_id}/{version}")
    if not _is_content_id(definition_id):
        raise ContentNotFoundError(
            f"campaigns/{campaign_id}/{version}/definitions/{definition_id}.json"
        )
    loaded = load_campaign(campaign_id, version)
    if definition_id not in loaded.definitions:
        raise ContentNotFoundError(
            f"campaigns/{campaign_id}/{version}/definitions/{definition_id}.json"
        )
    return loaded.definitions[definition_id]
