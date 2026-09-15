import json

import typer

from app.core.logging import configure_logging
from app.main import create_app
from app.modules.content.commands import content_app

cli = typer.Typer()


@cli.callback()
def main() -> None:
    configure_logging()


openapi_app = typer.Typer()
cli.add_typer(openapi_app, name="openapi")


@openapi_app.command("export")
def export() -> None:
    print(json.dumps(create_app().openapi(), indent=2))


cli.add_typer(content_app, name="content")
