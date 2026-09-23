"""Fixtures for the creation-chat routes (sprint 009-05).

- `client` (from `tests/conftest.py`): a `TestClient` over a fresh
  `create_app()` per test, DB session stubbed. `app.state` therefore
  starts empty every test -- nothing to reset by hand.
- `signed_in`: stubs `auth.service.resolve_session` /
  `users.service.get_user_by_id` for one fake, authenticated user.
  Returns an object with `.user_id` and `.headers` (session cookie + the
  matching `X-CSRF-Token`), ready for `client.post(..., headers=...)`.
- `run_overview`: `install(run_id, *, has_character=False,
  unavailable=False)`, used after `signed_in`. Monkeypatches
  `playthrough.service.get_run_overview` so only `run_id`, for the
  signed-in caller, answers -- any other run id or caller raises
  `CampaignRunNotFoundError`, the same 404 a foreign/unknown run gets for
  real. `has_character=True` puts the signed-in caller's own character on
  the member list (← AC1's 409).
- `scripted_model`: `install(*turns)`, called after `client` and before
  the first request. Monkeypatches
  `app.modules.character.service.chat_model` so the agent
  `start_creation`/`send_creation_message` lazily build on `app.state`
  picks up the scripted model. Each turn is one model step: a `str` is
  the Keeper's words (no tool call); a `(tool_name, args_dict)` tuple is
  one tool call -- its real tool runs before the next turn is consumed;
  an `Exception` instance is raised from the model call itself.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.core.ids import generate_id
from app.modules.auth import service as auth_service
from app.modules.character import service as character_service
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import CampaignRunNotFoundError
from app.modules.playthrough.schemas import (
    CampaignRunMemberRead,
    CampaignRunOverviewRead,
    CharacterRead,
)
from app.modules.users import service as users_service
from tests.factories import make_session, make_user

CSRF_TOKEN = "creation-chat-csrf-token"  # noqa: S105 - fixture value, not a secret


@pytest.fixture
def signed_in(monkeypatch):
    user_id = generate_id()
    session = make_session(user_id=user_id, csrf_token=CSRF_TOKEN)
    user = make_user(user_id=user_id)

    async def fake_resolve_session(db, *, token):
        return session

    async def fake_get_user_by_id(db, *, user_id):
        return user

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)

    headers = {"Cookie": "session=a-valid-cookie", "X-CSRF-Token": CSRF_TOKEN}
    return SimpleNamespace(user_id=user_id, headers=headers)


@pytest.fixture
def run_overview(monkeypatch, signed_in):
    def _install(
        run_id: str, *, has_character: bool = False, unavailable: bool = False
    ) -> CampaignRunOverviewRead:
        overview = CampaignRunOverviewRead(
            id=run_id,
            campaign_id="greenhollow",
            content_version="v1",
            title=None,
            status="setup",
            created_at=datetime.now(UTC),
            campaign_title=None if unavailable else "Greenhollow",
            campaign_summary=None if unavailable else "A ruined keep.",
            unavailable=unavailable,
            members=[
                CampaignRunMemberRead(
                    user_id=signed_in.user_id,
                    username="aragorn",
                    role="owner",
                    ready=has_character,
                    character=CharacterRead(
                        id="existing-hero",
                        name="Existing Hero",
                        current_hp=10,
                        max_hp=10,
                        armour_class=12,
                        race="Human",
                        character_class="Fighter",
                        level=1,
                        appearance="Weathered and grim.",
                    )
                    if has_character
                    else None,
                )
            ],
            adventures=[],
        )

        async def fake_get_run_overview(db, *, user_id, run_id: str):
            if run_id != overview.id or user_id != signed_in.user_id:
                raise CampaignRunNotFoundError(run_id)
            return overview

        monkeypatch.setattr(playthrough_service, "get_run_overview", fake_get_run_overview)
        return overview

    return _install


class _ToolAwareFakeModel(GenericFakeChatModel):
    """`GenericFakeChatModel` raises `NotImplementedError` on `bind_tools`,
    which the talk node calls; the script already carries the tool calls,
    so binding is a no-op here (mirrors
    `tests/character/test_creation_agent.py`)."""

    def bind_tools(self, tools, **kwargs):
        return self


def _turn_message(turn: str | tuple[str, dict[str, Any]]) -> AIMessage:
    if isinstance(turn, str):
        return AIMessage(content=turn)
    name, args = turn
    return AIMessage(content="", tool_calls=[{"id": str(uuid4()), "name": name, "args": args}])


def _turns(turns: tuple[str | tuple[str, dict[str, Any]] | Exception, ...]):
    for turn in turns:
        if isinstance(turn, Exception):
            raise turn
        yield _turn_message(turn)


@pytest.fixture
def scripted_model(monkeypatch):
    def _install(*turns: str | tuple[str, dict[str, Any]] | Exception) -> GenericFakeChatModel:
        model = _ToolAwareFakeModel(messages=_turns(turns))
        monkeypatch.setattr(character_service, "chat_model", lambda: model)
        return model

    return _install
