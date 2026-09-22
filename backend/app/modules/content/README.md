# content

Owns hand-authored, version-pinned adventure content — campaigns, adventures,
scenes and object templates — read from static JSON under `backend/content/` and
validated against a pinned schema and a fixed set of referential rules. No
table, no migration, no cache: content lives in git, not in the database.
The one authenticated route, `GET /api/v1/content/campaigns`, lists each
campaign at its newest valid version.

## Owns

- The Pydantic content schema (`schemas.py`): `Campaign`, `Adventure`,
  `Scene`, `ObjectTemplate` (`CreatureTemplate`/`ItemTemplate`/`FixtureTemplate`), `SeedCharacter` and their nested models.
- The loader (`service.py`): `list_campaign_ids`, `list_versions`,
  `load_campaign`, `load_scene`, `load_object_template`, `list_catalogue`.
- The referential rule set (R1–R20), applied by `load_campaign`.
- `ContentError` / `ContentNotFoundError` / `ContentInvalidError`
  (`errors.py`).
- The `app content validate` command (`commands.py`).

## Surface

- `service.load_campaign(campaign_id, version) -> LoadedCampaign` and its
  single-entity siblings `load_scene` / `load_object_template` — called by later
  phases via `from app.modules.content import service as content_service`.
- `service.list_catalogue() -> list[LoadedCampaign]` — every campaign at its
  newest version; a campaign with no version directories, or whose newest
  version fails to load, is skipped and logged rather than failing the call.
- `GET /api/v1/content/campaigns` (auth required) — the catalogue mapped to
  `CampaignSummaryRead` (id/title/summary/adventureCount).
- `app content validate` — walks every campaign and version under
  `CONTENT_ROOT/campaigns` and reports every problem found.

## Notes

- Field reference, directory layout, versioning and the full rule list are
  documented in [`docs/modules/content.md`](../../../../docs/modules/content.md).
- Callers use the module reference for functions *and* module attributes
  (`content_service.CONTENT_ROOT`), never a name import — tests repoint
  `CONTENT_ROOT` with `monkeypatch.setattr`.
- No caching: a campaign is re-read and re-validated on every call.
- `FixtureCheck.dc` and `Secret.dc` floor is 5, not 1 — the SRD's own
  difficulty table starts at 5, and the DM is bound to the same 5–30 range.
