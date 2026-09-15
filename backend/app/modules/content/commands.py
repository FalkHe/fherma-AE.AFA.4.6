import typer

from app.modules.content import service as content_service
from app.modules.content.errors import ContentInvalidError

content_app = typer.Typer()


@content_app.command("validate")
def validate() -> None:
    root = content_service.CONTENT_ROOT
    version_pattern = content_service.VERSION_PATTERN

    campaign_ids = content_service.list_campaign_ids()
    if not campaign_ids:
        typer.echo(f"no campaigns found under {root}", err=True)
        raise typer.Exit(code=1)

    ok = True
    for campaign_id in campaign_ids:
        campaign_dir = root / "campaigns" / campaign_id
        subdirs = sorted(entry.name for entry in campaign_dir.iterdir() if entry.is_dir())

        for name in subdirs:
            if not version_pattern.match(name):
                typer.echo(
                    f"{campaign_id}/{name}: [R3] version directory name must match "
                    f"{version_pattern.pattern}",
                    err=True,
                )
                ok = False

        versions = content_service.list_versions(campaign_id)
        if not versions:
            typer.echo(f"{campaign_id}: no version directory found", err=True)
            ok = False
            continue

        for version in versions:
            try:
                content_service.load_campaign(campaign_id, version)
            except ContentInvalidError as exc:
                ok = False
                for entry in exc.errors:
                    typer.echo(f"{campaign_id}/{version}: {entry}", err=True)
            else:
                typer.echo(f"{campaign_id}/{version}: ok")

    if not ok:
        raise typer.Exit(code=1)
