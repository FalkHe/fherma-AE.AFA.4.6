"""WI2: the stored SRD document becomes citable `RuleChunk`s (AC2, AC4).

Engine-free and offline throughout: every fixture is a small markdown
document written to `tmp_path` by the test itself -- never the real 1.9 MB
corpus, never the network. `tiktoken`'s BPE table is pre-warmed into the
image at build time (`docker/backend.Dockerfile`), so `count_tokens` and
`chunk_source` never reach it either.
"""

import tiktoken

from app.modules.srd import service


def _write(tmp_path, markdown: str):
    path = tmp_path / "fixture.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def test_heading_path_is_arrow_joined_and_anchor_free(tmp_path):
    markdown = (
        "# Combat\n\n"
        "## Cover\n\n"
        "### Half Cover {#half-cover}\n\n"
        "You have half cover if an obstacle blocks at least half of your body.\n"
    )
    chunks = service.chunk_source(_write(tmp_path, markdown))

    assert [c.heading_path for c in chunks] == ["Combat › Cover › Half Cover"]


def test_ordinals_run_from_zero_within_each_section(tmp_path):
    markdown = (
        "# Combat\n\n"
        "## Cover\n\n"
        "Some short filler text about cover.\n\n"
        "## Another Rule\n\n"
        "Some other short filler text.\n"
    )
    chunks = service.chunk_source(_write(tmp_path, markdown))

    by_path = {c.heading_path: c for c in chunks}
    assert by_path["Combat › Cover"].ordinal == 0
    assert by_path["Combat › Another Rule"].ordinal == 0


def test_heading_only_section_with_no_body_yields_no_passage(tmp_path):
    markdown = (
        "# Combat\n\n"
        "## Cover\n\n"
        "### Half Cover\n\n"
        "You have half cover if an obstacle blocks at least half of your body.\n"
    )
    chunks = service.chunk_source(_write(tmp_path, markdown))

    # "Combat" and "Combat › Cover" carry no body of their own -- only their
    # child heading does -- and so must not appear as citable passages.
    heading_paths = {c.heading_path for c in chunks}
    assert "Combat" not in heading_paths
    assert "Combat › Cover" not in heading_paths
    assert heading_paths == {"Combat › Cover › Half Cover"}


def test_oversized_section_splits_sharing_heading_path_ascending_ordinals_and_overlap(tmp_path):
    body = " ".join(f"tok{i:05d}" for i in range(5000))
    markdown = f"# Combat\n\n## Cover\n\n### Half Cover\n\n{body}\n"
    chunks = service.chunk_source(_write(tmp_path, markdown))

    heading_path = "Combat › Cover › Half Cover"
    section_chunks = [c for c in chunks if c.heading_path == heading_path]
    section_chunks.sort(key=lambda c: c.ordinal)

    assert len(section_chunks) >= 2, "fixture section must force at least one split"
    assert [c.ordinal for c in section_chunks] == list(range(len(section_chunks)))
    assert all(c.heading_path == heading_path for c in section_chunks)

    for earlier, later in zip(section_chunks, section_chunks[1:], strict=False):
        probe = earlier.text[-30:]
        assert probe in later.text, (probe, later.text[:60])


def test_no_passage_exceeds_max_chunk_tokens_or_embedding_window(tmp_path):
    small_body = "Short filler text for a small rule."
    large_body = " ".join(f"tok{i:05d}" for i in range(5000))
    markdown = f"# Combat\n\n## Cover\n\n{small_body}\n\n## Exploits\n\n{large_body}\n"
    chunks = service.chunk_source(_write(tmp_path, markdown))

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.token_count <= service.MAX_CHUNK_TOKENS
        assert chunk.token_count <= service.EMBEDDING_WINDOW_TOKENS


def test_count_tokens_matches_the_cl100k_base_encoding():
    text = "You have half cover if an obstacle blocks at least half of your body."
    expected = len(tiktoken.get_encoding("cl100k_base").encode(text))

    assert service.count_tokens(text) == expected
