"""AC1-AC6 -- sprint 009-03 WI2.

Driven through `typer.testing.CliRunner` against the real `cli`, with a
scripted fake model (`_ToolAwareFakeModel`, mirrors
`tests/game/test_service.py`'s) and `get_sessionmaker`,
`playthrough.service.get_campaign_run` and `.create_character`
monkeypatched -- no real database, no real model call. `content_service`
reads the real `greenhollow` campaign file (pure, no I/O worth stubbing),
so the greeting genuinely names its seed hero, Rosalind Thorn."""

import ast
from pathlib import Path
from types import SimpleNamespace

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from typer.testing import CliRunner

from app.cli import cli
from app.modules.character import builder, commands
from app.modules.character import service as character_service
from app.modules.character.schemas import CharacterCreateRequest
from app.modules.playthrough import service as playthrough_service

runner = CliRunner()

_CHARACTER_MODULE = Path(__file__).resolve().parents[2] / "app" / "modules" / "character"


class _ToolAwareFakeModel(GenericFakeChatModel):
    """`GenericFakeChatModel` raises `NotImplementedError` on `bind_tools`,
    which the talk node calls; the script already carries the tool calls,
    so binding is a no-op here (mirrors `tests/game/test_service.py`)."""

    def bind_tools(self, tools, **kwargs):
        return self


def _scripted_model(messages: list[AIMessage]) -> GenericFakeChatModel:
    return _ToolAwareFakeModel(messages=iter(messages))


def _tool_call(call_id: str, name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"id": call_id, "name": name, "args": args}])


class _FakeSessionmaker:
    def __call__(self):
        return self

    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


async def _fake_get_campaign_run(db, *, user_id, run_id):
    return SimpleNamespace(campaign_id="greenhollow", content_version="v1")


def _invoke(input_text: str):
    return runner.invoke(
        cli,
        ["character", "create", "--run", "run-1", "--user", "user-1"],
        input=input_text,
    )


def _patch_common(monkeypatch, scripted_model) -> None:
    monkeypatch.setattr(playthrough_service, "get_campaign_run", _fake_get_campaign_run)
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    monkeypatch.setattr(character_service, "chat_model", lambda: scripted_model)


def _patch_create_character(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    async def fake_create_character(db, **kwargs):
        calls.append(kwargs)
        return None

    monkeypatch.setattr(playthrough_service, "create_character", fake_create_character)
    return calls


def test_ac1_taking_the_ready_made_hero_saves_it_directly_and_names_it_in_the_greeting(
    monkeypatch,
):
    save_call = _tool_call("call-1", "save_character", {"confirmed": True, "ready_made": True})
    reply = AIMessage(content="Rosalind Thorn steps up, ready as she'll ever be.")
    scripted = _scripted_model([save_call, reply])
    _patch_common(monkeypatch, scripted)
    calls = _patch_create_character(monkeypatch)

    result = _invoke("take Rosalind\n")

    assert result.exit_code == 0, result.output
    assert "Rosalind Thorn" in result.stdout
    assert calls == [{"user_id": "user-1", "run_id": "run-1", "sheet": None}]
    assert commands.FINALITY_LINE in result.stdout


def test_ac2_race_and_class_are_written_down_only_after_the_player_agrees(monkeypatch):
    question = AIMessage(content="A halfling rogue, maybe? Say the word and it's written down.")
    set_call = _tool_call(
        "call-2", "set_race_and_class", {"race": "Halfling", "character_class": "Rogue"}
    )
    confirmed = AIMessage(content="Written down: Halfling, Rogue.")
    scripted = _scripted_model([question, set_call, confirmed])
    _patch_common(monkeypatch, scripted)
    _patch_create_character(monkeypatch)

    result = _invoke("a sneaky halfling burglar\ny\n")

    assert result.exit_code == 0, result.output
    assert question.content in result.stdout
    assert confirmed.content in result.stdout
    # The tool call only fires on the second turn: had it fired on the
    # first, the script's second message (`set_call`, no text) would have
    # been consumed as the first turn's reply instead of `question`.
    assert result.stdout.index(question.content) < result.stdout.index(confirmed.content)


def test_ac3_every_number_on_the_sheet_comes_from_build_sheet(monkeypatch):
    request = CharacterCreateRequest(
        name="Pip",
        race="Halfling",
        character_class="Rogue",
        alignment="Neutral",
        abilities=builder.suggested_scores("Rogue"),
    )
    expected_sheet = character_service.build_sheet(request)
    sheet_text = character_service.render_sheet(expected_sheet)

    scripted = _scripted_model(
        [
            _tool_call(
                "c1", "set_race_and_class", {"race": "Halfling", "character_class": "Rogue"}
            ),
            _tool_call("c2", "set_identity", {"name": "Pip"}),
            _tool_call("c3", "suggest_scores", {}),
            _tool_call("c4", "show_sheet", {}),
            AIMessage(content=sheet_text),
        ]
    )
    _patch_common(monkeypatch, scripted)
    _patch_create_character(monkeypatch)

    result = _invoke("a halfling rogue named Pip, show me the sheet\n")

    assert result.exit_code == 0, result.output
    assert str(expected_sheet.max_hp) in result.stdout
    assert str(expected_sheet.armour_class) in result.stdout


def test_ac4_the_sheet_is_shown_before_saving_and_an_unconfirmed_save_writes_nothing(
    monkeypatch,
):
    shown = AIMessage(content="Here's how it stands so far.")
    refused = AIMessage(content="Not written down until you say so.")
    scripted = _scripted_model(
        [
            _tool_call("c1", "show_sheet", {}),
            shown,
            _tool_call("c2", "save_character", {"confirmed": False}),
            refused,
        ]
    )
    _patch_common(monkeypatch, scripted)
    calls = _patch_create_character(monkeypatch)

    result = _invoke("show me the sheet\nnot yet\n")

    assert result.exit_code == 0, result.output
    assert result.stdout.index(shown.content) < result.stdout.index(refused.content)
    assert calls == []


def test_ac5_quitting_before_saving_keeps_nothing(monkeypatch):
    scripted = _scripted_model([])
    _patch_common(monkeypatch, scripted)
    calls = _patch_create_character(monkeypatch)

    result = _invoke("quit\n")

    assert result.exit_code == 0, result.output
    assert calls == []


def test_ac6_the_prompt_names_the_agent_but_no_identifier_in_the_module_does():
    prompt_path = _CHARACTER_MODULE / "prompts" / "v1" / "system" / "creator.md"
    assert "Tavern Keeper" in prompt_path.read_text()

    banned_words = ("tavern", "keeper")
    offenders: list[str] = []
    for py_file in _CHARACTER_MODULE.rglob("*.py"):
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                name = node.name
            elif isinstance(node, ast.arg):
                name = node.arg
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.alias):
                name = node.asname or node.name

            if name and any(word in name.lower() for word in banned_words):
                offenders.append(f"{py_file.relative_to(_CHARACTER_MODULE)}:{node.lineno}:{name}")

    assert offenders == []
