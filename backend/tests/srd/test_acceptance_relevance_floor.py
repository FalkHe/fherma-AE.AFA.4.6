"""qa acceptance tests -- sprint 004/06 "'no relevant rule' is an answer,
not an empty guess" (AC1-AC5),
`docs/intents/004-srd-knowledge-base/sprints/06-relevance-floor/brief.md`.

Black-box throughout: every test drives the real `app srd search` command
through `typer.testing.CliRunner` against `app.cli.cli`, or the public
`from app.modules.srd import service as srd_service` seam -- never a
private helper, never the implementation modules themselves, and never a
read of `service.py`/`commands.py`/`models.py` while writing this file (per
the qa brief: these tests are written against the sprint brief and the
fixed contracts handed to qa, not the code). No real embedding call is ever
made (`app.core.llm.service.embed_texts` monkeypatched at the module level,
the same idiom sprint 04/05's `test_acceptance_rules_search.py` uses), and
the network is never touched.

AC1/AC2 name two real questions ("how do I reload a plasma rifle" / "how
does half cover work"); the actual by-eye run against the live, real SRD
corpus is performed separately by the sprint lead once implementation
lands (the plan's own last line). What is assertable here without a real
embedding call: the real query *text* is still the one handed to the CLI
and the gateway seam, while the vector that text resolves to is a
controlled one this file picks -- one that lands below the pinned floor
for AC1's plasma-rifle question (nothing in the corpus is remotely close
to it), one that lands above it for AC2's half-cover question (the corpus
does carry an answer). The floor itself is pinned and offline-measurable,
so AC3-AC5 are exercised with fully synthetic, exact-score vectors.

Every criterion here needs a real, populated (or deliberately empty)
vector column, so every database-backed test uses the `database`-marked
`srd_db` fixture (`tests/srd/conftest.py`, test infrastructure this file
only consumes) and carries `@pytest.mark.database`; that fixture overrides
the suite's global `EMBEDDING_DIMENSIONS=4` pin to `1536`, the migrated
width.

Scores are pinned to exact, known values with 1536-wide synthetic basis
vectors, exactly sprint 04/05's recipe: a query vector normalized to
`(1/sqrt(2), 1/sqrt(2), 0, ...)` scores `1.0` against a row on that same
vector, `1/sqrt(2) ~= 0.707` against a row on the lone basis vector `e0`,
and `0.0` against any row on a basis vector orthogonal to both components
(e.g. `e2`) -- real cosine distance against the real, migrated `srd_rules`
table does the rest. `0.707` and `0.0` straddle the pinned floor
(`RELEVANCE_FLOOR = 0.40` per the plan); every assertion below reads the
floor from `srd_service.RELEVANCE_FLOOR` itself rather than hard-coding
`0.40` a second time, except where the criterion (AC3) is about that exact
pinned value.

`app.core.db.get_engine`/`get_sessionmaker` are `@lru_cache`d for the whole
process and are what the CLI's own commands use for a database session --
`_cli_uses_scratch_db()` clears both caches immediately before and after
every CLI invocation that needs to reach `srd_db`'s scratch database,
exactly as sprint 04/05's acceptance file does.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
import math
import re
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from app.cli import cli
from app.core.db import get_engine, get_sessionmaker
from app.core.ids import generate_id
from app.core.llm import service as llm_service
from app.core.settings import Settings
from app.modules.srd import service as srd_service

runner = CliRunner()

BACKEND_ROOT = Path(__file__).resolve().parents[2]
VECTOR_WIDTH = 1536

# `1/sqrt(2)` -- the shared component that makes a two-basis-vector blend a
# unit vector, so cosine similarity against it comes out to exact, known
# values (`1.0` / `0.707` / `0.0`), the same recipe sprint 04/05 measured
# against the real, migrated table.
_UNIT_COMPONENT = 1 / math.sqrt(2)


def _vector(nonzero: dict[int, float]) -> str:
    """A pgvector literal, `VECTOR_WIDTH` wide, with `nonzero`'s entries set
    and every other component `0` -- a synthetic basis-style vector, never
    a real embedding."""
    values = ["0"] * VECTOR_WIDTH
    for index, value in nonzero.items():
        values[index] = repr(value)
    return "[" + ",".join(values) + "]"


def _dense_vector(nonzero: dict[int, float]) -> list[float]:
    """The plain Python `list[float]` equivalent of `_vector` -- what a
    monkeypatched `embed_texts` hands back as `EmbeddingResult.vectors[0]`,
    as opposed to `_vector`'s pgvector literal used for seeding rows."""
    values = [0.0] * VECTOR_WIDTH
    for index, value in nonzero.items():
        values[index] = value
    return values


async def _insert_rule(db, *, heading_path: str, ordinal: int, body: str, vector: str) -> None:
    """One known row, inserted by raw SQL against the real, migrated table
    -- exactly `test_acceptance_rules_search.py`'s pattern -- never through
    the module under test."""
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
    what text actually reached the gateway seam."""

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
    binding again afterwards -- exactly sprint 04/05's acceptance file."""
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    try:
        yield
    finally:
        asyncio.run(get_engine().dispose())
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()


@pytest.mark.database
def test_ac1_out_of_corpus_question_says_no_relevant_rule(srd_db, monkeypatch):
    # <- AC1: `app srd search "how do I reload a plasma rifle"` must print
    # "no relevant rule" and return no passages. The real by-eye run
    # against the live corpus is the sprint lead's own separate check
    # (module docstring); what is assertable offline is that a query whose
    # embedding lands nowhere near anything in the corpus (orthogonal to
    # every stored row, score `0.0`, below the pinned floor) comes back
    # empty even though the corpus itself is non-empty -- with the real
    # question text still the one handed to the CLI.
    cover_heading = "Combat › Cover › Half Cover"

    async def _seed():
        await _insert_rule(
            srd_db,
            heading_path=cover_heading,
            ordinal=0,
            body="You have half cover if an obstacle blocks at least half of your body.",
            vector=_vector({0: 1.0, 1: 1.0}),
        )
        await srd_db.commit()

    asyncio.run(_seed())

    # Orthogonal to the seeded row's nonzero components (0, 1) -- cosine
    # similarity `0.0`, well below `RELEVANCE_FLOOR`.
    monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_fixed(_dense_vector({5: 1.0})))

    with _cli_uses_scratch_db():
        result = runner.invoke(cli, ["srd", "search", "how do I reload a plasma rifle"])

    assert result.exit_code == 0, result.output
    assert "no relevant rule" in result.stdout.lower(), result.stdout
    assert cover_heading not in result.stdout, result.stdout


@pytest.mark.database
def test_ac2_in_corpus_question_still_answered_after_floor_raised(srd_db, monkeypatch):
    # <- AC2: the same build must still answer `app srd search "how does
    # half cover work"` with a passage -- raising the floor did not empty
    # the useful case. The row's embedding is set to the exact query
    # vector this test feeds the gateway seam (cosine similarity `1.0`),
    # comfortably above `RELEVANCE_FLOOR`, proving a genuinely relevant
    # match still comes back.
    cover_heading = "Combat › Cover › Half Cover"
    cover_body = "You have half cover if an obstacle blocks at least half of your body."
    query_vector = _dense_vector({0: _UNIT_COMPONENT, 1: _UNIT_COMPONENT})

    async def _seed():
        await _insert_rule(
            srd_db,
            heading_path=cover_heading,
            ordinal=0,
            body=cover_body,
            vector=_vector({0: _UNIT_COMPONENT, 1: _UNIT_COMPONENT}),
        )
        await srd_db.commit()

    asyncio.run(_seed())

    monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_fixed(query_vector))

    with _cli_uses_scratch_db():
        result = runner.invoke(cli, ["srd", "search", "how does half cover work"])

    assert result.exit_code == 0, result.output
    assert cover_heading in result.stdout, result.stdout
    assert "no relevant rule" not in result.stdout.lower(), result.stdout


def test_ac3_relevance_floor_is_a_pinned_constant_and_readme_records_the_measurement():
    # <- AC3: `RELEVANCE_FLOOR` must be a pinned module constant -- not a
    # setting, not read from the environment -- and the module README must
    # record which queries were measured to choose it. No database needed:
    # this is a static read of the module attribute, the `Settings` schema,
    # and the README text.
    assert hasattr(srd_service, "RELEVANCE_FLOOR"), "srd_service.RELEVANCE_FLOOR is missing"
    floor = srd_service.RELEVANCE_FLOOR
    assert isinstance(floor, float)
    assert floor == pytest.approx(0.40)

    # Not a setting: the `Settings` schema (env/`.env`-driven, per
    # `core/settings.py`) carries no field for it at all, so it structurally
    # cannot be read from the environment or `.env` the way every real
    # setting is.
    assert "relevance_floor" not in Settings.model_fields, Settings.model_fields.keys()

    readme_path = BACKEND_ROOT / "app" / "modules" / "srd" / "README.md"
    assert readme_path.exists(), readme_path
    readme_text = readme_path.read_text()

    assert "RELEVANCE_FLOOR" in readme_text, readme_text
    assert "0.40" in readme_text or "0.4" in readme_text, readme_text

    # "records which queries were measured to choose it" -- evidence of an
    # actual measurement, not just a prose claim: at least a handful of
    # decimal scores in the same shape the floor itself is expressed in
    # (the plan's own measured figures, e.g. `0.485`, `0.371`, `0.631`).
    scored_numbers = re.findall(r"\b0\.\d{2,3}\b", readme_text)
    assert len(scored_numbers) >= 3, readme_text


@pytest.mark.database
def test_ac4_below_floor_matches_are_dropped_entirely_never_flagged(srd_db, monkeypatch):
    # <- AC4: the sharp one. A match below the floor must not appear in
    # the returned list at all (checked against the public `search_rules`
    # seam), must not appear in the CLI's output in any form, and there
    # must be no "best effort" or warning wording anywhere in that output.
    # Also: when *every* match is below the floor, the result is empty
    # rather than a single best guess.
    above_heading = "AC4 › Above Floor › Kept"
    above_body = "This passage sits above the relevance floor and must be returned."
    below_heading = "AC4 › Below Floor › Dropped"
    below_body = "This passage sits below the relevance floor and must never be returned."
    only_below_heading = "AC4 › Only Below Floor › Also Dropped"
    only_below_body = "A second below-floor passage, present only for the all-below case."

    query_vector = _dense_vector({0: _UNIT_COMPONENT, 1: _UNIT_COMPONENT})

    async def _seed():
        # Score against `query_vector`: cosine similarity `1.0` (identical
        # vector) -- above `RELEVANCE_FLOOR`.
        await _insert_rule(
            srd_db,
            heading_path=above_heading,
            ordinal=0,
            body=above_body,
            vector=_vector({0: _UNIT_COMPONENT, 1: _UNIT_COMPONENT}),
        )
        # Score against `query_vector`: orthogonal, cosine similarity
        # `0.0` -- below `RELEVANCE_FLOOR`.
        await _insert_rule(
            srd_db,
            heading_path=below_heading,
            ordinal=0,
            body=below_body,
            vector=_vector({2: 1.0}),
        )
        await srd_db.commit()

    asyncio.run(_seed())

    monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_fixed(query_vector))

    # Structural: the below-floor row is entirely absent from the returned
    # list, not merely reordered or annotated.
    matches = asyncio.run(srd_service.search_rules(srd_db, "AC4 mixed query"))
    matched_headings = [match.heading_path for match in matches]
    assert above_heading in matched_headings, matched_headings
    assert below_heading not in matched_headings, matched_headings

    with _cli_uses_scratch_db():
        mixed_result = runner.invoke(cli, ["srd", "search", "AC4 mixed query"])

    assert mixed_result.exit_code == 0, mixed_result.output
    assert above_heading in mixed_result.stdout, mixed_result.stdout
    assert below_heading not in mixed_result.stdout, mixed_result.stdout
    assert below_body not in mixed_result.stdout, mixed_result.stdout
    lowered_mixed = mixed_result.stdout.lower()
    assert "best effort" not in lowered_mixed, mixed_result.stdout
    assert "warning" not in lowered_mixed, mixed_result.stdout

    # Every match below the floor: the result is empty, not a single best
    # guess. A fresh query vector orthogonal to every seeded row (including
    # the previously above-floor one) plus one more below-floor row.
    async def _seed_only_below():
        await _insert_rule(
            srd_db,
            heading_path=only_below_heading,
            ordinal=0,
            body=only_below_body,
            vector=_vector({3: 1.0}),
        )
        await srd_db.commit()

    asyncio.run(_seed_only_below())

    all_below_query_vector = _dense_vector({7: 1.0})
    monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_fixed(all_below_query_vector))

    all_below_matches = asyncio.run(srd_service.search_rules(srd_db, "AC4 all-below query"))
    assert all_below_matches == [], all_below_matches

    with _cli_uses_scratch_db():
        all_below_result = runner.invoke(cli, ["srd", "search", "AC4 all-below query"])

    assert all_below_result.exit_code == 0, all_below_result.output
    assert "no relevant rule" in all_below_result.stdout.lower(), all_below_result.stdout
    for heading in (above_heading, below_heading, only_below_heading):
        assert heading not in all_below_result.stdout, all_below_result.stdout
    lowered_all_below = all_below_result.stdout.lower()
    assert "best effort" not in lowered_all_below, all_below_result.stdout
    assert "warning" not in lowered_all_below, all_below_result.stdout


@pytest.mark.database
def test_ac5_nothing_relevant_and_empty_corpus_stay_distinguishable(srd_db, monkeypatch):
    # <- AC5: nothing-relevant is exit 0 with "no relevant rule" on stdout;
    # an empty rulebook is exit non-zero with its own message on stderr.
    # Checked in one test against the same `srd_db`, in this order: the
    # corpus starts empty (freshly migrated, nothing ingested yet), so that
    # case is checked first; then a below-floor row is inserted so the
    # nothing-relevant case can be checked against a genuinely non-empty
    # corpus.
    calls: list = []
    monkeypatch.setattr(
        llm_service, "embed_texts", _fake_embed_fixed(_dense_vector({0: 1.0}), calls=calls)
    )

    with _cli_uses_scratch_db():
        empty_corpus_result = runner.invoke(cli, ["srd", "search", "how does half cover work"])

    assert empty_corpus_result.exit_code != 0, empty_corpus_result.output
    assert empty_corpus_result.stdout == ""
    assert "empty" in empty_corpus_result.stderr.lower(), empty_corpus_result.stderr
    assert "ingest" in empty_corpus_result.stderr.lower(), empty_corpus_result.stderr
    assert "no relevant rule" not in empty_corpus_result.stderr.lower(), empty_corpus_result.stderr
    assert "no relevant rule" not in empty_corpus_result.stdout.lower(), empty_corpus_result.stdout

    below_heading = "AC5 › Below Floor › Never Returned"

    async def _seed():
        # Orthogonal to the query vector `{0: 1.0}` fed below -- cosine
        # similarity `0.0`, below `RELEVANCE_FLOOR`.
        await _insert_rule(
            srd_db,
            heading_path=below_heading,
            ordinal=0,
            body="A passage that never clears the relevance floor.",
            vector=_vector({4: 1.0}),
        )
        await srd_db.commit()

    asyncio.run(_seed())

    with _cli_uses_scratch_db():
        nothing_relevant_result = runner.invoke(cli, ["srd", "search", "how does half cover work"])

    assert nothing_relevant_result.exit_code == 0, nothing_relevant_result.output
    assert "no relevant rule" in nothing_relevant_result.stdout.lower(), (
        nothing_relevant_result.stdout
    )
    assert nothing_relevant_result.stderr == ""
    assert below_heading not in nothing_relevant_result.stdout, nothing_relevant_result.stdout

    # The two are not confusable: different exit codes, different streams
    # carry the message.
    assert empty_corpus_result.exit_code != nothing_relevant_result.exit_code
