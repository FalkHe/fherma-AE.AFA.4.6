"""qa acceptance tests -- sprint 004/05 "a rules question comes back with
passages we can cite" (AC1-AC6),
`docs/intents/004-srd-knowledge-base/sprints/05-rules-search/brief.md`.

Black-box throughout: every test drives the real `app srd search` command
through `typer.testing.CliRunner` against `app.cli.cli`, or the public
`from app.modules.srd import service as srd_service` seam -- never a
private helper, never the implementation modules themselves, and never a
read of `service.py`/`commands.py`/`models.py` while writing this file (per
the qa brief: these tests are written against the sprint brief and the
fixed contracts handed to qa, not the code). No real embedding call is ever
made (`app.core.llm.service.embed_texts` monkeypatched at the module level,
the same idiom sprint 04/03's `test_acceptance_corpus_ingested.py` uses),
and the network is never touched.

Every criterion here needs a real, populated (or deliberately empty) vector
column, so every test uses the `database`-marked `srd_db` fixture
(`tests/srd/conftest.py`, test infrastructure this file only consumes) and
carries `@pytest.mark.database`; that fixture overrides the suite's global
`EMBEDDING_DIMENSIONS=4` pin to `1536`, the migrated width.

Ordering is proved with real, controlled data rather than faked: rows carry
known 1536-wide basis vectors (`_vector`) and queries are fed a known,
fixed "embedding" through the monkeypatched `embed_texts` -- what pgvector's
own `cosine_distance` then does with them is exercised for real.

`test_ac1`'s three-row recipe (`e0`/`e1`/`e2` rows against a query built
from `srd_service.RELEVANCE_FLOOR` itself) was updated for sprint 004/06
(`docs/intents/004-srd-knowledge-base/sprints/06-relevance-floor/
brief.md`, AC4): that sprint drops any match scoring below the pinned
floor entirely, so the original recipe's third row -- orthogonal to the
query, scoring `0.0` -- would now be dropped rather than ranked, which is
a *different* claim (AC4, sprint 06's own file,
`test_acceptance_relevance_floor.py`) than what AC1 here is actually
about: that passages which do come back are ordered best match first. The
replacement derives its query vector from the current floor at run time
rather than restating a fixed clearance in prose against a value expected
to move -- see the comment at `test_ac1` itself for how -- so a later
re-measurement cannot silently erode the margin between these three
scores and the floor; do not reintroduce a `0.0`-scoring row here.

AC4 is explicitly a by-eye check against the real SRD corpus in one run
(the brief's own words) -- untestable in CI without a real embedding call.
What is assertable here is the shape of the claim: three unrelated queries,
each embedded to point at a different, controlled row, each come back
naming that row's section. The real by-eye run against the live corpus is
performed separately by the sprint lead; this file does not fake that
result.

`app.core.db.get_engine`/`get_sessionmaker` are `@lru_cache`d for the whole
process and are what the CLI's own commands use for a database session --
`_cli_uses_scratch_db()` clears both caches immediately before and after
every CLI invocation that needs to reach `srd_db`'s scratch database,
exactly as sprint 04/03's and 04/04's acceptance files do.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from app.cli import cli
from app.core.db import get_engine, get_sessionmaker
from app.core.ids import generate_id
from app.core.llm import service as llm_service
from app.modules.srd import service as srd_service

runner = CliRunner()

BACKEND_ROOT = Path(__file__).resolve().parents[2]
VECTOR_WIDTH = 1536


def _vector(nonzero: dict[int, float]) -> str:
    """A pgvector literal, `VECTOR_WIDTH` wide, with `nonzero`'s entries set
    and every other component `0` -- a synthetic basis-style vector, never
    a real embedding."""
    values = ["0"] * VECTOR_WIDTH
    for index, value in nonzero.items():
        values[index] = repr(value)
    return "[" + ",".join(values) + "]"


async def _insert_rule(db, *, heading_path: str, ordinal: int, body: str, vector: str) -> None:
    """One known row, inserted by raw SQL against the real, migrated table
    -- exactly `test_acceptance_empty_corpus_status.py`'s AC4 pattern --
    never through the module under test."""
    await db.execute(
        text(
            "INSERT INTO srd_rules "
            "(id, source_version, heading_path, ordinal, text, token_count, "
            "embedding_model, embedding) "
            "VALUES (:id, :source_version, :heading_path, :ordinal, :text, "
            ":token_count, :embedding_model, CAST(:embedding AS vector))"
        ),
        {
            "id": generate_id(),
            "source_version": "v1",
            "heading_path": heading_path,
            "ordinal": ordinal,
            "text": body,
            "token_count": max(len(body.split()), 1),
            "embedding_model": "test/embedding-model",
            "embedding": vector,
        },
    )


def _fake_embed_fixed(vector: list[float], *, calls: list | None = None):
    """A stand-in for `llm_service.embed_texts` that always returns `vector`
    regardless of the text handed in -- the query's content never drives
    ranking here, the controlled vector does. `calls`, if given, records
    every batch of texts the fake was asked to embed, so a test can prove
    whether (and how often) the gateway was actually reached."""

    def _embed(texts, *, model=None):
        if calls is not None:
            calls.append(list(texts))
        vectors = [vector for _ in texts]
        usage = llm_service.Usage(
            prompt_tokens=len(texts), completion_tokens=0, total_tokens=len(texts), cost_usd=0.0
        )
        return llm_service.EmbeddingResult(vectors=vectors, usage=usage)

    return _embed


@contextmanager
def _cli_uses_scratch_db():
    """Force the CLI's cached `get_engine`/`get_sessionmaker` to rebuild
    against whichever `DATABASE_URL` `srd_db` just pinned, and drop that
    binding again afterwards -- exactly sprint 04/03's acceptance file."""
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    try:
        yield
    finally:
        asyncio.run(get_engine().dispose())
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()


@pytest.mark.database
def test_ac1_search_prints_passages_most_relevant_first(srd_db, monkeypatch):
    # <- AC1: `app srd search "how does half cover work"` must print
    # passages, best match first. Ranking is proved with rows on basis
    # vectors e0/e1/e2 against a query vector derived below from
    # `srd_service.RELEVANCE_FLOOR` itself, so all three scores clear the
    # floor by construction -- not by a margin claimed in a comment, which
    # sprint 06's own re-measurement (0.40 -> 0.43) already showed can go
    # stale. This recipe used to include a fourth, orthogonal (score 0.0)
    # row to prove *everything* comes back, but sprint 06 deliberately
    # drops anything below the floor, so that claim moved to
    # `test_acceptance_relevance_floor.py`'s own AC4. What is left here is
    # AC1's real claim -- ordering -- so every row must keep scoring well
    # clear of the floor; do not add a low- or zero-scoring row back in,
    # it would make this an AC4 test by accident.
    e0_heading = "Combat › Cover › Half Cover"
    e1_heading = "Combat › Actions in Combat › Dash"
    e2_heading = "Equipment › Armor › Shields"

    async def _seed():
        await _insert_rule(
            srd_db,
            heading_path=e0_heading,
            ordinal=0,
            body="You have half cover if an obstacle blocks at least half of your body.",
            vector=_vector({0: 1.0}),
        )
        await _insert_rule(
            srd_db,
            heading_path=e1_heading,
            ordinal=0,
            body="You can take the Dash action to gain extra movement.",
            vector=_vector({1: 1.0}),
        )
        await _insert_rule(
            srd_db,
            heading_path=e2_heading,
            ordinal=0,
            body="A shield grants a bonus to your Armor Class.",
            vector=_vector({2: 1.0}),
        )
        await srd_db.commit()

    asyncio.run(_seed())

    # Derived from `RELEVANCE_FLOOR`, not a literal: three raw components,
    # each `CLEARANCE` further above the current floor than the next,
    # fed as the query against unit rows e0/e1/e2. Cosine similarity
    # against a unit basis row is `component / ||query||`; whenever the
    # components' squares sum to under 1 (asserted below), `||query|| < 1`,
    # so dividing by it only *raises* each score above its own raw value --
    # the achieved scores end up at or above `floor + CLEARANCE`,
    # `floor + 2 * CLEARANCE`, `floor + 3 * CLEARANCE` respectively,
    # strictly decreasing (proves ordering) and each guaranteed clear of
    # the floor however far the next re-measurement moves it. The
    # assertion below fails loudly -- rather than silently shrinking the
    # margin -- if a future floor ever leaves no room for this geometry.
    floor = srd_service.RELEVANCE_FLOOR
    clearance = 0.06
    raw_components = [floor + 3 * clearance, floor + 2 * clearance, floor + clearance]
    assert sum(component * component for component in raw_components) < 1, (
        f"RELEVANCE_FLOOR={floor} leaves no room for three distinct, "
        "ordered scores this far above it -- lower `clearance`"
    )
    blended_query_vector = raw_components + [0.0] * (VECTOR_WIDTH - 3)
    monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_fixed(blended_query_vector))

    with _cli_uses_scratch_db():
        result = runner.invoke(cli, ["srd", "search", "how does half cover work"])

    assert result.exit_code == 0, result.output
    assert e0_heading in result.stdout
    assert e1_heading in result.stdout
    assert e2_heading in result.stdout
    assert (
        result.stdout.index(e0_heading)
        < result.stdout.index(e1_heading)
        < result.stdout.index(e2_heading)
    ), result.stdout


@pytest.mark.database
def test_ac2_each_passage_carries_heading_path_ordinal_and_score(srd_db, monkeypatch):
    # <- AC2: `RuleMatch` -- `heading_path`, `ordinal`, `text`, `score` --
    # asserted against the public `search_rules` seam itself, structurally,
    # not against CLI formatting (that's AC1's own concern). A row queried
    # by its own identical vector must score `1.0` (cosine distance `0`,
    # `score = 1 - distance`), a directly checkable value.
    heading = "Adventuring › Conditions › Poisoned"
    body = "A poisoned creature has disadvantage on attack rolls and ability checks."

    async def _scenario():
        await _insert_rule(
            srd_db, heading_path=heading, ordinal=3, body=body, vector=_vector({0: 1.0})
        )
        await srd_db.commit()

        matches = await srd_service.search_rules(srd_db, "what does poisoned do")
        return matches

    monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_fixed(_dense_vector({0: 1.0})))

    matches = asyncio.run(_scenario())

    assert len(matches) == 1
    match = matches[0]
    assert match.heading_path == heading
    assert match.ordinal == 3
    assert match.text == body
    assert isinstance(match.score, float)
    assert match.score == pytest.approx(1.0, abs=1e-3)


@pytest.mark.database
def test_ac3_limit_caps_results_and_omitted_falls_back_to_default_limit(srd_db, monkeypatch):
    # <- AC3: eight distinguishable rows, all on the same vector (ties are
    # irrelevant here -- only the *count* returned matters). `--limit 3`
    # must cap the passages printed at 3; the flag omitted must cap them at
    # the module's own `DEFAULT_LIMIT`, read from the seam, never hard-coded.
    headings = [f"AC3 › Synthetic Passage {i}" for i in range(8)]

    async def _seed():
        for i, heading in enumerate(headings):
            await _insert_rule(
                srd_db,
                heading_path=heading,
                ordinal=0,
                body=f"Synthetic filler passage number {i}.",
                vector=_vector({0: 1.0}),
            )
        await srd_db.commit()

    asyncio.run(_seed())

    monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_fixed(_dense_vector({0: 1.0})))

    with _cli_uses_scratch_db():
        capped = runner.invoke(cli, ["srd", "search", "synthetic passage", "--limit", "3"])
        default = runner.invoke(cli, ["srd", "search", "synthetic passage"])

    assert capped.exit_code == 0, capped.output
    assert default.exit_code == 0, default.output

    capped_count = sum(1 for heading in headings if heading in capped.stdout)
    default_count = sum(1 for heading in headings if heading in default.stdout)

    assert capped_count == 3, capped.stdout
    assert default_count == srd_service.DEFAULT_LIMIT, default.stdout


@pytest.mark.database
def test_ac4_a_condition_a_combat_action_and_a_spell_each_return_their_own_section(
    srd_db, monkeypatch
):
    # <- AC4: the real by-eye run against the live SRD corpus (three
    # unrelated questions in one run) is performed separately by the
    # sprint lead -- not reproducible here without a real embedding call.
    # What is assertable offline: three controlled rows, one per category,
    # and three queries each embedded to point straight at one of them --
    # each must come back naming that row's own section.
    condition_heading = "Adventuring › Conditions › Prone"
    combat_heading = "Combat › Making an Attack › Melee Attacks › Grappling"
    spell_heading = "Spell Lists › Spell Descriptions › Fire Bolt"

    async def _seed():
        await _insert_rule(
            srd_db,
            heading_path=condition_heading,
            ordinal=0,
            body="A prone creature's only movement option is to crawl.",
            vector=_vector({0: 1.0}),
        )
        await _insert_rule(
            srd_db,
            heading_path=combat_heading,
            ordinal=0,
            body="You can use a special melee attack to grapple your target.",
            vector=_vector({1: 1.0}),
        )
        await _insert_rule(
            srd_db,
            heading_path=spell_heading,
            ordinal=0,
            body="You hurl a mote of fire at a creature or object within range.",
            vector=_vector({2: 1.0}),
        )
        await srd_db.commit()

    asyncio.run(_seed())

    queries = [
        ("what does the prone condition do", _dense_vector({0: 1.0}), condition_heading),
        ("how does grappling work", _dense_vector({1: 1.0}), combat_heading),
        ("what does fire bolt do", _dense_vector({2: 1.0}), spell_heading),
    ]

    with _cli_uses_scratch_db():
        for query_text, vector, expected_heading in queries:
            monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_fixed(vector))
            result = runner.invoke(cli, ["srd", "search", query_text, "--limit", "1"])

            assert result.exit_code == 0, result.output
            assert expected_heading in result.stdout, result.stdout


@pytest.mark.database
def test_ac5_nothing_outside_srd_reaches_srd_rules_and_search_goes_through_the_shared_gateway(
    srd_db, monkeypatch
):
    # <- AC5: structural first -- grepping the real, unmocked tree (never a
    # fixture) for every reference to the model, the table, or a direct
    # cosine-distance query outside the module that owns them, exactly
    # `test_acceptance_corpus_ingested.py`'s AC5, plus a check that the
    # module itself never talks to the provider directly. Then behavioural:
    # calling the public `search_rules` seam must actually reach
    # `core/llm`'s `embed_texts`, the shared gateway, not some parallel path.
    backend_app_root = BACKEND_ROOT / "app"
    srd_module_root = backend_app_root / "modules" / "srd"

    offenders = []
    for path in backend_app_root.rglob("*.py"):
        if srd_module_root in path.parents:
            continue
        content = path.read_text()
        if "SrdRule" in content or "srd_rules" in content or "cosine_distance" in content:
            offenders.append(str(path.relative_to(BACKEND_ROOT)))
    assert offenders == [], offenders

    direct_provider_refs = []
    for path in srd_module_root.rglob("*.py"):
        content = path.read_text()
        if "openrouter" in content.lower():
            direct_provider_refs.append(str(path.relative_to(BACKEND_ROOT)))
    assert direct_provider_refs == [], direct_provider_refs

    heading = "Combat › Cover › Half Cover"

    async def _scenario():
        await _insert_rule(
            srd_db,
            heading_path=heading,
            ordinal=0,
            body="You have half cover if an obstacle blocks at least half of your body.",
            vector=_vector({0: 1.0}),
        )
        await srd_db.commit()
        return await srd_service.search_rules(srd_db, "how does half cover work")

    calls: list = []
    monkeypatch.setattr(
        llm_service, "embed_texts", _fake_embed_fixed(_dense_vector({0: 1.0}), calls=calls)
    )

    matches = asyncio.run(_scenario())

    assert len(calls) == 1, calls
    assert "how does half cover work" in calls[0], calls
    assert len(matches) == 1
    assert matches[0].heading_path == heading


@pytest.mark.database
def test_ac6_searching_empty_corpus_exits_nonzero_with_empty_message_before_gateway_call(
    srd_db, monkeypatch
):
    # <- AC6: nothing has been ingested into `srd_db`'s freshly-migrated,
    # empty table. The command must exit non-zero with the empty-corpus
    # message on stderr and print nothing on stdout -- never an empty
    # result -- and the fake gateway (`calls`) must record zero invocations:
    # the guard fires before any embedding call is spent.
    calls: list = []
    monkeypatch.setattr(
        llm_service, "embed_texts", _fake_embed_fixed(_dense_vector({0: 1.0}), calls=calls)
    )

    with _cli_uses_scratch_db():
        result = runner.invoke(cli, ["srd", "search", "how does half cover work"])

    assert result.exit_code != 0, result.output
    assert result.stdout == ""
    assert "Traceback" not in result.output
    assert "empty" in result.stderr.lower()
    assert "ingest" in result.stderr.lower()
    assert calls == [], calls


def _dense_vector(nonzero: dict[int, float]) -> list[float]:
    """The plain Python `list[float]` equivalent of `_vector` -- what a
    monkeypatched `embed_texts` hands back as `EmbeddingResult.vectors[0]`,
    as opposed to `_vector`'s pgvector literal used for seeding rows."""
    values = [0.0] * VECTOR_WIDTH
    for index, value in nonzero.items():
        values[index] = value
    return values
