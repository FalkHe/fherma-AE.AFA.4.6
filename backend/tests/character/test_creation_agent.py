"""AC1-AC6 -- sprint 009-03, plus one round-1-review regression test.

Driven through `typer.testing.CliRunner` against the real `cli`, with a
scripted fake model (`_ToolAwareFakeModel`, mirrors
`tests/game/test_service.py`'s) and `get_sessionmaker`,
`playthrough.service.get_campaign_run` and `.create_character`
monkeypatched -- no real database, no real model call. `content_service`
reads the real `greenhollow` campaign file (pure, no I/O worth stubbing),
so the greeting genuinely names its seed hero, Rosalind Thorn.

AC3/AC4 let `show_sheet` run for real through the `ToolNode` -- the
scripted model's own lines never contain the sheet's numbers, so a
passing assertion proves the tool, not the test, put them on screen."""

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
from app.modules.playthrough import dice
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


class _ScriptedRandom:
    """A fixed, in-order sequence of face values -- `dice._rng`'s
    replacement, not the stdlib module (AGENTS.md's dice gotcha), mirrors
    `tests/playthrough/test_service_rolls.py`'s helper."""

    def __init__(self, values):
        self._values = values

    def randint(self, a: int, b: int) -> int:
        return next(self._values)


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
    show_call = _tool_call("call-0", "show_sheet", {"ready_made": True})
    save_call = _tool_call("call-1", "save_character", {"confirmed": True, "ready_made": True})
    reply = AIMessage(content="Rosalind Thorn steps up, ready as she'll ever be.")
    scripted = _scripted_model([show_call, save_call, reply])
    _patch_common(monkeypatch, scripted)
    calls = _patch_create_character(monkeypatch)

    result = _invoke("take Rosalind\n")

    assert result.exit_code == 0, result.output
    assert "Rosalind Thorn" in result.stdout
    # `show_sheet(ready_made=True)` -> `render_seed` is what actually put
    # her stats on screen -- the script's own closing line never mentions
    # them (← D14 §1.3).
    assert "Hit points" in result.stdout
    assert result.stdout.index("Hit points") < result.stdout.index(commands.FINALITY_LINE)
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

    # The script's own closing line never mentions a number: `show_sheet`
    # runs for real through the `ToolNode`, so the HP/AC that land in the
    # output can only have come from `service.build_sheet`, never the
    # model's own words.
    scripted = _scripted_model(
        [
            _tool_call(
                "c1", "set_race_and_class", {"race": "Halfling", "character_class": "Rogue"}
            ),
            _tool_call("c2", "set_identity", {"name": "Pip"}),
            _tool_call("c3", "suggest_scores", {}),
            _tool_call("c4", "show_sheet", {}),
            AIMessage(content="There it is."),
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
    request = CharacterCreateRequest(
        name="Pip",
        race="Halfling",
        character_class="Rogue",
        alignment="Neutral",
        abilities=builder.suggested_scores("Rogue"),
    )
    expected_sheet = character_service.build_sheet(request)
    refused = AIMessage(content="Not written down until you say so.")
    scripted = _scripted_model(
        [
            _tool_call(
                "c1", "set_race_and_class", {"race": "Halfling", "character_class": "Rogue"}
            ),
            _tool_call("c2", "set_identity", {"name": "Pip"}),
            _tool_call("c3", "suggest_scores", {}),
            _tool_call("c4", "show_sheet", {}),
            AIMessage(content="Here's how it stands so far."),
            _tool_call("c5", "save_character", {"confirmed": False}),
            refused,
        ]
    )
    _patch_common(monkeypatch, scripted)
    calls = _patch_create_character(monkeypatch)

    result = _invoke("a halfling rogue named Pip, show me the sheet\nnot yet\n")

    assert result.exit_code == 0, result.output
    assert result.stdout.index(str(expected_sheet.max_hp)) < result.stdout.index(refused.content)
    assert calls == []


def test_regression_two_draft_writing_tool_calls_in_one_step_do_not_crash(monkeypatch):
    """← item 1: `set_identity` and `suggest_scores` both write to
    `draft` in the same model step (a plain last-value channel raises
    `InvalidUpdateError` here); the merge reducer on `CreationState.draft`
    must let both land and the session must keep running."""
    set_race = _tool_call(
        "c1", "set_race_and_class", {"race": "Halfling", "character_class": "Rogue"}
    )
    ack_race = AIMessage(content="Halfling Rogue, noted.")
    both_at_once = AIMessage(
        content="",
        tool_calls=[
            {"id": "c2", "name": "set_identity", "args": {"name": "Pip"}},
            {"id": "c3", "name": "suggest_scores", "args": {}},
        ],
    )
    final = AIMessage(content="Got it all down.")
    scripted = _scripted_model([set_race, ack_race, both_at_once, final])
    _patch_common(monkeypatch, scripted)
    _patch_create_character(monkeypatch)

    result = _invoke("a halfling rogue\ny\n")

    assert result.exit_code == 0, result.output
    assert commands.MODEL_ERROR_REPLY not in result.stdout
    assert final.content in result.stdout


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


def test_s04_ac1_scores_by_hand_show_points_left_and_rolled_scores_come_from_the_dice(
    monkeypatch,
):
    """← AC1. Spending by hand always writes and shows the points left;
    rolling comes from `dice._rng`, never a number the model makes up."""
    by_hand = _scripted_model(
        [
            _tool_call(
                "c1",
                "set_scores",
                {
                    "strength": 15,
                    "dexterity": 14,
                    "constitution": 13,
                    "intelligence": 12,
                    "wisdom": 10,
                    "charisma": 8,
                },
            ),
            # The model relays the tool's own message verbatim (← research
            # Decision 2) -- scripted here exactly as `set_scores` would
            # phrase it, standing in for that relay.
            AIMessage(
                content=(
                    "Scores written down: STR 15, DEX 14, CON 13, INT 12, "
                    "WIS 10, CHA 8. Points left: 0."
                )
            ),
        ]
    )
    _patch_common(monkeypatch, by_hand)
    _patch_create_character(monkeypatch)

    result = _invoke("I'll spend the points myself\n")

    assert result.exit_code == 0, result.output
    assert "Points left:" in result.stdout

    # Every 4d6-drop-lowest roll gets faces [6, 6, 6, 1] -> drops the 1,
    # sums to 18 for every ability; Halfling's own +2 dexterity then lands
    # dexterity at 20 -- neither number the suggested/default set produces.
    monkeypatch.setattr(dice, "_rng", lambda: _ScriptedRandom(iter([6, 6, 6, 1] * 6)))
    rolled = _scripted_model(
        [
            _tool_call(
                "c1", "set_race_and_class", {"race": "Halfling", "character_class": "Rogue"}
            ),
            _tool_call("c2", "set_identity", {"name": "Pip"}),
            _tool_call("c3", "roll_scores", {}),
            _tool_call("c4", "show_sheet", {}),
            AIMessage(content="There it is."),
        ]
    )
    _patch_common(monkeypatch, rolled)
    _patch_create_character(monkeypatch)

    result = _invoke("a halfling rogue named Pip, roll for me, show me the sheet\n")

    assert result.exit_code == 0, result.output
    assert "STR 18 (+4)" in result.stdout
    assert "DEX 20 (+5)" in result.stdout


def test_s04_ac2_a_later_set_identity_call_overwrites_the_name_on_the_sheet(monkeypatch):
    """← AC2. Two `set_identity` calls in the same session; the sheet
    keeps the second, not the first."""
    scripted = _scripted_model(
        [
            _tool_call(
                "c1", "set_race_and_class", {"race": "Halfling", "character_class": "Rogue"}
            ),
            _tool_call("c2", "set_identity", {"name": "Pip"}),
            _tool_call("c3", "set_identity", {"name": "Pip Underbough"}),
            _tool_call("c4", "show_sheet", {}),
            AIMessage(content="There it is."),
        ]
    )
    _patch_common(monkeypatch, scripted)
    _patch_create_character(monkeypatch)

    result = _invoke("a halfling rogue, first Pip then Pip Underbough\n")

    assert result.exit_code == 0, result.output
    assert "Pip Underbough" in result.stdout


def test_s04_ac3_set_skills_lands_alongside_the_classs_own_auto_filled_skills(monkeypatch):
    """← AC3. The two story skills and the Rogue's own class-granted
    skills (SRD order, story skills excluded) both land on the sheet."""
    scripted = _scripted_model(
        [
            _tool_call(
                "c1", "set_race_and_class", {"race": "Halfling", "character_class": "Rogue"}
            ),
            _tool_call("c2", "set_identity", {"name": "Pip"}),
            _tool_call("c3", "set_skills", {"first": "Stealth", "second": "Deception"}),
            _tool_call("c4", "show_sheet", {}),
            AIMessage(content="There it is."),
        ]
    )
    _patch_common(monkeypatch, scripted)
    _patch_create_character(monkeypatch)

    result = _invoke("a halfling rogue named Pip, stealthy and a bit of a liar\n")

    assert result.exit_code == 0, result.output
    assert (
        "Skills: Stealth, Deception, Acrobatics, Athletics, Insight, Intimidation" in result.stdout
    )


def test_s04_ac4_set_alignment_shows_in_the_sheets_header_line(monkeypatch):
    """← AC4."""
    scripted = _scripted_model(
        [
            _tool_call(
                "c1", "set_race_and_class", {"race": "Halfling", "character_class": "Rogue"}
            ),
            _tool_call("c2", "set_identity", {"name": "Pip"}),
            _tool_call("c3", "set_alignment", {"alignment": "Chaotic Good"}),
            _tool_call("c4", "show_sheet", {}),
            AIMessage(content="There it is."),
        ]
    )
    _patch_common(monkeypatch, scripted)
    _patch_create_character(monkeypatch)

    result = _invoke("a halfling rogue named Pip, chaotic good\n")

    assert result.exit_code == 0, result.output
    assert "Halfling Rogue - Level 1 - Chaotic Good" in result.stdout


def test_s04_ac5_pick_equipment_then_take_default_equipment_reach_the_sheet(monkeypatch):
    """← AC5. `pick_equipment(1, 2)` takes the Rogue's (b) shortsword for
    choice 1; `take_default_equipment` leaves everything else at its own
    default (a)."""
    scripted = _scripted_model(
        [
            _tool_call(
                "c1", "set_race_and_class", {"race": "Halfling", "character_class": "Rogue"}
            ),
            _tool_call("c2", "set_identity", {"name": "Pip"}),
            _tool_call("c3", "pick_equipment", {"choice_number": 1, "option_number": 2}),
            _tool_call("c4", "take_default_equipment", {}),
            _tool_call("c5", "show_sheet", {}),
            AIMessage(content="There it is."),
        ]
    )
    _patch_common(monkeypatch, scripted)
    _patch_create_character(monkeypatch)

    result = _invoke("a halfling rogue named Pip, just the default otherwise\n")

    assert result.exit_code == 0, result.output
    equipment_line = next(
        line for line in result.stdout.splitlines() if line.startswith("Equipment:")
    )
    assert "Shortsword" in equipment_line
    assert "Rapier" not in equipment_line
    assert "Burglar's Pack" in equipment_line
    assert "Leather" in equipment_line


def test_s04_ac6_one_show_sheet_carries_alignment_skills_and_equipment_together(monkeypatch):
    """← AC6."""
    scripted = _scripted_model(
        [
            _tool_call(
                "c1", "set_race_and_class", {"race": "Halfling", "character_class": "Rogue"}
            ),
            _tool_call("c2", "set_identity", {"name": "Pip"}),
            _tool_call("c3", "set_alignment", {"alignment": "Chaotic Good"}),
            _tool_call("c4", "set_skills", {"first": "Stealth", "second": "Deception"}),
            _tool_call("c5", "take_default_equipment", {}),
            _tool_call("c6", "show_sheet", {}),
            AIMessage(content="Here's Pip, ready for the road."),
        ]
    )
    _patch_common(monkeypatch, scripted)
    _patch_create_character(monkeypatch)

    result = _invoke(
        "a halfling rogue named Pip, chaotic good, stealthy and a liar, default gear\n"
    )

    assert result.exit_code == 0, result.output
    assert "Chaotic Good" in result.stdout
    assert "Skills: Stealth, Deception" in result.stdout
    assert "Equipment: Rapier" in result.stdout
