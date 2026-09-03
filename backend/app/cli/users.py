"""`app users` — account administration, including the first-admin bootstrap.

There is no HTTP route that grants the admin role, so the very first admin is
made here: `app users set-role <name> admin`.

This module is the reference implementation of the CLI async pattern: the Typer
command body stays synchronous and calls `asyncio.run(_impl(...))`; the async
half opens one session from the sessionmaker and hands it to a service. No SQL
and no transaction management live in this layer — session revocation on
demotion and on password reset belongs to `user_service`.
"""

import asyncio
from typing import Annotated, NoReturn

import typer

from app.db.models.user import User, UserRole
from app.db.session import get_sessionmaker
from app.services import user_service

app = typer.Typer(
    help="Administer user accounts.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command("set-role")
def set_role(
    username: Annotated[
        str,
        typer.Argument(help="Account to change; matched case-insensitively."),
    ],
    role: Annotated[
        UserRole,
        typer.Argument(help="Role to assign."),
    ],
) -> None:
    """Set an account's role; assigning the role it already has is a success.

    Demotion from admin to user revokes that account's sessions (in the
    service), so a stale cookie cannot keep exercising admin routes.
    """
    try:
        user = asyncio.run(_set_role(username, role))
    except user_service.UserNotFoundError as error:
        _fail_unknown_user(username, error)

    typer.echo(f"{user.username} now has role {user.role.value}.")


@app.command("reset-password")
def reset_password(
    username: Annotated[
        str,
        typer.Argument(help="Account to change; matched case-insensitively."),
    ],
) -> None:
    """Replace an account's password and revoke all of its sessions.

    The password is prompted for, never taken as an argument: arguments end up
    in shell history and in the process list.
    """
    password = typer.prompt("New password", hide_input=True, confirmation_prompt=True)
    try:
        user = asyncio.run(_reset_password(username, password))
    except user_service.UserNotFoundError as error:
        _fail_unknown_user(username, error)

    typer.echo(f"Password for {user.username} reset; all sessions revoked.")


async def _set_role(username: str, role: UserRole) -> User:
    """Async half of `set-role`: one session, one service call."""
    async with get_sessionmaker()() as session:
        return await user_service.set_role(session, username, role)


async def _reset_password(username: str, password: str) -> User:
    """Async half of `reset-password`: one session, one service call."""
    async with get_sessionmaker()() as session:
        return await user_service.reset_password(session, username, password)


def _fail_unknown_user(username: str, error: Exception) -> NoReturn:
    """Report an unknown username on stderr and exit non-zero."""
    typer.echo(f"No account named {username!r}.", err=True)
    raise typer.Exit(code=1) from error


if __name__ == "__main__":  # pragma: no cover
    app()
