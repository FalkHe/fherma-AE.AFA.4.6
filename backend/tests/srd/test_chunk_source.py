"""WI1 (sprint 004-02): `service.chunk_source`. `count_tokens` is always
monkeypatched here to a cheap whitespace word count -- never the real
`cl100k_base` encoding -- so no test triggers tiktoken's BPE download
(AGENTS.md gotcha)."""

import pytest

from app.modules.srd import service
from app.modules.srd.errors import SrdSourceError


@pytest.fixture(autouse=True)
def word_count_tokens(monkeypatch):
    monkeypatch.setattr(service, "count_tokens", lambda text: len(text.split()))


def test_heading_path_joins_the_open_stack_with_anchors_and_whitespace_stripped(tmp_path):
    markdown = (
        "# Combat\n\n## Cover {#section-cover}\n\n### Half Cover  \n\nYou get a +2 bonus to AC.\n"
    )
    path = tmp_path / "srd.md"
    path.write_text(markdown)

    chunks = service.chunk_source(path)

    assert len(chunks) == 1
    assert chunks[0].heading_path == "Combat › Cover › Half Cover"
    assert chunks[0].ordinal == 0
    assert chunks[0].text == "You get a +2 bonus to AC."


def test_heading_only_sections_produce_no_chunk(tmp_path):
    markdown = "# Combat\n\n## Cover\n\n### Half Cover\n\nSome text.\n"
    path = tmp_path / "srd.md"
    path.write_text(markdown)

    chunks = service.chunk_source(path)

    headings = [chunk.heading_path for chunk in chunks]
    assert "Combat" not in headings
    assert "Combat › Cover" not in headings
    assert headings == ["Combat › Cover › Half Cover"]


def test_oversized_section_splits_into_ordinals_each_within_the_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "MAX_CHUNK_TOKENS", 10)
    monkeypatch.setattr(service, "CHUNK_OVERLAP_TOKENS", 3)
    body_words = [f"word{i}" for i in range(37)]
    markdown = "# Big Section\n\n" + " ".join(body_words) + "\n"
    path = tmp_path / "srd.md"
    path.write_text(markdown)

    chunks = service.chunk_source(path)

    assert len(chunks) > 1
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.heading_path == "Big Section" for chunk in chunks)
    assert all(chunk.token_count <= 10 for chunk in chunks)
    # Each piece after the first repeats the tail of the previous one.
    for previous, current in zip(chunks, chunks[1:], strict=False):
        previous_words = previous.text.split()
        current_words = current.text.split()
        assert current_words[0] in previous_words[-3:]


def test_skipped_heading_levels_still_yield_siblings(tmp_path):
    markdown = "# A\n\n## B\n\n#### C\n\nBody C.\n\n#### D\n\nBody D.\n"
    path = tmp_path / "srd.md"
    path.write_text(markdown)

    chunks = service.chunk_source(path)

    headings = [chunk.heading_path for chunk in chunks]
    assert headings == ["A › B › C", "A › B › D"]


def test_deeper_then_shallower_heading_closes_the_stack_by_level(tmp_path):
    markdown = "# A\n\n#### C\n\nBody C.\n\n### E\n\nBody E.\n\n#### F\n\nBody F.\n"
    path = tmp_path / "srd.md"
    path.write_text(markdown)

    chunks = service.chunk_source(path)

    headings = [chunk.heading_path for chunk in chunks]
    assert headings == ["A › C", "A › E", "A › E › F"]


def test_empty_file_raises_srd_source_error(tmp_path):
    path = tmp_path / "srd.md"
    path.write_text("")

    with pytest.raises(SrdSourceError):
        service.chunk_source(path)


def test_headingless_file_raises_srd_source_error(tmp_path):
    path = tmp_path / "srd.md"
    path.write_text("Just some prose with no heading at all.\n")

    with pytest.raises(SrdSourceError):
        service.chunk_source(path)
