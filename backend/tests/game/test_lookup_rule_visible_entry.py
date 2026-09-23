"""Sprint 010/04, WI3: a rule lookup leaves a player-visible transcript
entry naming the topic -- never the rules text, never the model's own
search words (`docs/intents/010-dm-agent-in-gui/sprints/04-visible-
system-lines/plan.md`, interfaces I1/I3, AC1, part of AC3).

`lookup_rule` (`app.modules.game.agent.tools`) is called directly through
its `.coroutine`, the same seam `test_run_turn_engine.py`'s node tests use
(`node(..., runtime=runtime)`) -- no graph, no LLM, no database. `runtime`
is a bare `SimpleNamespace(context=...)` since the tool never reads
anything on it beyond `.context` (module docstring: `ToolRuntime` is
injected by `ToolNode` and hidden from the model's schema).

`playthrough_service.record_rule_lookup` is I3's contract, owned by WI2 and
written in parallel -- monkeypatched here to a spy, exactly as
`test_run_turn_engine.py` fakes `tools.playthrough_service.roll` rather
than driving that function's own body. This file proves WI3's own wiring:
that `lookup_rule` calls it with the right `topic` when (and only when)
the search matched, never with `take`'s own concerns.

The combined-turn check additionally fakes `playthrough_service.take` (a
successful `item_moved` write and a refusal) and `playthrough_service.
passive_check` (a private mechanic, no visible write) so the count of
player-visible entries a whole turn leaves can be asserted without waiting
on WI1/WI2's own suites, which cover each mechanic's internal correctness
on their own.
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.modules.game.agent import tools
from app.modules.game.agent.state import DmContext
from app.modules.playthrough.errors import ObjectNotReachableError
from app.modules.srd.errors import SrdCorpusEmptyError
from app.modules.srd.schemas import RuleMatch

USER_ID = "user-1"
RUN_ID = "run-1"
TURN_ID = "turn-1"

BEST_HEADING = "Chapter 7 › Using Ability Scores › Hiding"
OTHER_HEADING = "Chapter 7 › Using Ability Scores › Passive Checks"


def _ctx(**overrides) -> DmContext:
    fields = {
        "db": object(),
        "user_id": USER_ID,
        "actor_id": "actor-1",
        "run_id": RUN_ID,
        "turn_id": TURN_ID,
    }
    fields.update(overrides)
    return DmContext(**fields)


def _runtime(ctx: DmContext) -> SimpleNamespace:
    return SimpleNamespace(context=ctx)


def _matches() -> list[RuleMatch]:
    return [
        RuleMatch(heading_path=BEST_HEADING, ordinal=3, text="You can hide...", score=0.1),
        RuleMatch(heading_path=OTHER_HEADING, ordinal=7, text="A passive check...", score=0.4),
    ]


def _install_record_rule_lookup(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    async def fake_record_rule_lookup(db, *, user_id, run_id, topic, turn_id=None):
        calls.append(
            {"user_id": user_id, "run_id": run_id, "topic": topic, "turn_id": turn_id}
        )
        return SimpleNamespace(id="event-rule-1", payload={"topic": topic})

    monkeypatch.setattr(
        tools.playthrough_service, "record_rule_lookup", fake_record_rule_lookup, raising=False
    )
    return calls


def test_a_matched_lookup_leaves_one_visible_entry_carrying_the_heading(monkeypatch):
    async def fake_search_rules(db, *, query, limit):
        return _matches()

    monkeypatch.setattr(tools.srd_service, "search_rules", fake_search_rules)
    calls = _install_record_rule_lookup(monkeypatch)

    ctx = _ctx()
    result = asyncio.run(
        tools.lookup_rule.coroutine(query="can I hide behind a barrel?", runtime=_runtime(ctx))
    )

    assert len(calls) == 1
    assert calls[0] == {
        "user_id": USER_ID,
        "run_id": RUN_ID,
        "topic": BEST_HEADING,
        "turn_id": TURN_ID,
    }
    assert result["rules"][0]["heading"] == BEST_HEADING


def test_a_lookup_that_matched_nothing_leaves_none(monkeypatch):
    async def fake_search_rules(db, *, query, limit):
        return []

    monkeypatch.setattr(tools.srd_service, "search_rules", fake_search_rules)
    calls = _install_record_rule_lookup(monkeypatch)

    ctx = _ctx()
    result = asyncio.run(tools.lookup_rule.coroutine(query="a word matching nothing", runtime=_runtime(ctx)))

    assert calls == []
    assert result["rules"] == []


def test_an_empty_corpus_leaves_none(monkeypatch):
    """`SrdCorpusEmptyError` is the other "matched nothing" path -- the
    search never even ran, so it must not write a row either."""

    async def fake_search_rules(db, *, query, limit):
        raise SrdCorpusEmptyError()

    monkeypatch.setattr(tools.srd_service, "search_rules", fake_search_rules)
    calls = _install_record_rule_lookup(monkeypatch)

    ctx = _ctx()
    result = asyncio.run(tools.lookup_rule.coroutine(query="anything", runtime=_runtime(ctx)))

    assert calls == []
    assert result["rules"] == []


def test_a_matched_lookup_with_no_run_id_leaves_none(monkeypatch):
    """No `run_id` (`ctx.run_id` unset) means there is no transcript to
    write into -- the same guard `recall` uses for its own early return."""

    async def fake_search_rules(db, *, query, limit):
        return _matches()

    monkeypatch.setattr(tools.srd_service, "search_rules", fake_search_rules)
    calls = _install_record_rule_lookup(monkeypatch)

    ctx = _ctx(run_id=None)
    asyncio.run(tools.lookup_rule.coroutine(query="can I hide?", runtime=_runtime(ctx)))

    assert calls == []


def test_the_models_own_query_words_never_reach_the_entry(monkeypatch):
    query = "does hiding behind a barrel work against a sleeping goblin"

    async def fake_search_rules(db, *, query, limit):
        return _matches()

    monkeypatch.setattr(tools.srd_service, "search_rules", fake_search_rules)
    calls = _install_record_rule_lookup(monkeypatch)

    ctx = _ctx()
    asyncio.run(tools.lookup_rule.coroutine(query=query, runtime=_runtime(ctx)))

    assert calls[0]["topic"] == BEST_HEADING
    assert query not in calls[0]["topic"]
    for word in query.split():
        assert word not in calls[0]["topic"]


def test_the_heading_reaches_the_model_as_a_readable_string_not_character_by_character(monkeypatch):
    """Regression for the `" > ".join(m.heading_path)` bug: `heading_path`
    is already one joined string (`srd/schemas.py`), so joining it again
    character-by-character used to hand the model `"C > h > a > p ..."`."""

    async def fake_search_rules(db, *, query, limit):
        return _matches()

    monkeypatch.setattr(tools.srd_service, "search_rules", fake_search_rules)
    _install_record_rule_lookup(monkeypatch)

    ctx = _ctx()
    result = asyncio.run(tools.lookup_rule.coroutine(query="hiding", runtime=_runtime(ctx)))

    headings = [rule["heading"] for rule in result["rules"]]
    assert headings == [BEST_HEADING, OTHER_HEADING]
    assert " > ".join(BEST_HEADING) not in headings


# --- Combined turn: a lookup and a take together, plus the two silent cases


def test_a_turn_with_a_rule_lookup_and_a_take_leaves_exactly_two_visible_entries(monkeypatch):
    visible: list[dict] = []

    async def fake_search_rules(db, *, query, limit):
        return _matches()

    monkeypatch.setattr(tools.srd_service, "search_rules", fake_search_rules)

    async def fake_record_rule_lookup(db, *, user_id, run_id, topic, turn_id=None):
        visible.append({"kind": "rule_looked_up", "topic": topic})
        return SimpleNamespace(id="event-rule-1", payload={"topic": topic})

    monkeypatch.setattr(
        tools.playthrough_service, "record_rule_lookup", fake_record_rule_lookup, raising=False
    )

    async def fake_take(db, *, user_id, actor_id, item_id, turn_id=None):
        visible.append({"kind": "item_moved", "item_id": item_id})

    monkeypatch.setattr(tools.playthrough_service, "take", fake_take)

    ctx = _ctx()

    lookup_result = asyncio.run(
        tools.lookup_rule.coroutine(query="can the hero hide here?", runtime=_runtime(ctx))
    )
    take_result = asyncio.run(
        tools.take.coroutine(item_id="item-1", runtime=_runtime(ctx))
    )

    assert lookup_result["status"] == "ok"
    assert take_result["status"] == "ok"
    assert len(visible) == 2
    assert {entry["kind"] for entry in visible} == {"rule_looked_up", "item_moved"}


def test_a_refused_take_and_a_private_check_leave_no_visible_entry(monkeypatch):
    visible: list[dict] = []

    async def fake_take(db, *, user_id, actor_id, item_id, turn_id=None):
        raise ObjectNotReachableError(item_id)

    monkeypatch.setattr(tools.playthrough_service, "take", fake_take)

    async def fake_passive_check(db, *, user_id, actor_id, ability, dc, turn_id=None):
        # A private mechanic: it never appends to the visible ledger.
        return True

    monkeypatch.setattr(tools.playthrough_service, "passive_check", fake_passive_check)

    ctx = _ctx()

    with pytest.raises(ObjectNotReachableError):
        asyncio.run(tools.take.coroutine(item_id="item-1", runtime=_runtime(ctx)))

    check_result = asyncio.run(
        tools.passive_check.coroutine(
            ability="wisdom", dc=12, runtime=_runtime(ctx)
        )
    )

    assert check_result["success"] is True
    assert visible == []
