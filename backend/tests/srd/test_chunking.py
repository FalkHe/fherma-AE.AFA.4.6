"""WI2: the stored SRD document becomes citable `RuleChunk`s (AC2, AC4).

WI1 (sprint 04): no two stored passages can claim the same citation --
`ordinal` is numbered per `heading_path` across the whole document, not
restarted per markdown section, so a collided heading trail continues the
sequence instead of duplicating position 0.

Engine-free and offline throughout: every fixture is a small markdown
document written to `tmp_path` by the test itself -- never the real 1.9 MB
corpus, never the network -- with one deliberate exception: the shipped-
corpus regression test below reads the real, committed source file to prove
this sprint's change leaves its shape unchanged. `tiktoken`'s BPE table is
pre-warmed into the image at build time (`docker/backend.Dockerfile`), so
`count_tokens` and `chunk_source` never reach it either.

WI3: a passage's own name lives in its heading, not its body, so
`RuleChunk.token_count` now covers the trail-joined text that actually goes
to the embedder (`heading_path` + `EMBED_TRAIL_SEPARATOR` + `text`), while
`RuleChunk.text` itself stays body-only -- that is what gets stored and
quoted back as a citation.
"""

import pytest
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


def test_token_count_honestly_includes_the_heading_trail_not_just_the_body(tmp_path):
    # <- WI3: the reported token figure must describe what is actually sent
    # to the embedder (heading trail + body), not the stored body alone.
    markdown = "# Spells\n\n## Fire Bolt\n\nA ray of fire streaks toward a creature.\n"
    chunks = service.chunk_source(_write(tmp_path, markdown))
    (chunk,) = chunks

    body_only_tokens = service.count_tokens(chunk.text)
    embedded_tokens = service.count_tokens(
        chunk.heading_path + service.EMBED_TRAIL_SEPARATOR + chunk.text
    )

    assert chunk.token_count == embedded_tokens
    assert chunk.token_count > body_only_tokens


def test_stored_text_stays_body_only_even_though_token_count_counts_the_trail(tmp_path):
    # <- WI3: `SrdRule.text` is quoted back as a citation and must never
    # carry the heading path a second time.
    markdown = "# Conditions\n\n## Poisoned\n\nA poisoned creature has disadvantage.\n"
    (chunk,) = service.chunk_source(_write(tmp_path, markdown))

    assert chunk.text == "A poisoned creature has disadvantage."
    assert chunk.heading_path not in chunk.text


def test_oversized_section_split_parts_do_not_double_count_the_trail(tmp_path):
    # <- WI3: every split part already carries the same `heading_path`
    # (AC2/AC4); joining it once per part when computing `token_count` must
    # not join it twice on any part, and must never push a part's actually-
    # embedded token count past `MAX_CHUNK_TOKENS`.
    body = " ".join(f"tok{i:05d}" for i in range(5000))
    markdown = f"# Combat\n\n## Cover\n\n### Half Cover\n\n{body}\n"
    chunks = service.chunk_source(_write(tmp_path, markdown))

    heading_path = "Combat › Cover › Half Cover"
    section_chunks = [c for c in chunks if c.heading_path == heading_path]
    assert len(section_chunks) >= 2, "fixture section must force at least one split"

    for chunk in section_chunks:
        joined_once = chunk.heading_path + service.EMBED_TRAIL_SEPARATOR + chunk.text
        joined_twice = (
            chunk.heading_path
            + service.EMBED_TRAIL_SEPARATOR
            + chunk.heading_path
            + service.EMBED_TRAIL_SEPARATOR
            + chunk.text
        )
        assert chunk.token_count == service.count_tokens(joined_once)
        assert chunk.token_count != service.count_tokens(joined_twice)
        assert chunk.token_count <= service.MAX_CHUNK_TOKENS


def test_a_long_heading_trail_never_lets_the_stride_skip_past_the_window(tmp_path):
    # <- verification: the stride between windows (`step`) is a fixed
    # `MAX_CHUNK_TOKENS - CHUNK_OVERLAP_TOKENS`, while the window's own
    # ceiling shrinks with the heading trail's token cost -- a trail long
    # enough (> `CHUNK_OVERLAP_TOKENS` tokens) would let `step` outrun the
    # window and silently skip body tokens between two windows if nothing
    # clamped it. This heading trail is deliberately far longer than any in
    # the real corpus, to actually force that clamp.
    long_heading = " ".join(f"headingword{i:05d}" for i in range(120))
    body_words = [f"tok{i:05d}" for i in range(1500)]
    body = " ".join(body_words)
    markdown = f"# {long_heading}\n\n{body}\n"
    chunks = service.chunk_source(_write(tmp_path, markdown))

    assert len(chunks) >= 2, "fixture must force at least one split"
    # No separator: each chunk's text is itself an exact decode of a token
    # window, so back-to-back concatenation reconstructs every covered
    # token faithfully (an inserted separator could itself split a body
    # token that straddles a window boundary and falsely look "missing").
    covered = "".join(c.text for c in chunks)
    missing = [word for word in body_words if word not in covered]
    assert missing == [], f"{len(missing)} body tokens were dropped between windows"


def test_a_heading_trail_that_alone_exceeds_max_chunk_tokens_fails_loudly(tmp_path):
    # <- verification: leaving zero room for any body text must never
    # silently produce an empty or truncated passage -- it is a source the
    # module cannot chunk at all.
    huge_heading = " ".join(f"headingword{i:05d}" for i in range(1000))
    markdown = f"# {huge_heading}\n\nShort body.\n"

    with pytest.raises(service.SrdSourceError):
        service.chunk_source(_write(tmp_path, markdown))


def test_headings_that_collapse_to_the_same_trail_produce_distinct_positions(tmp_path):
    # <- WI1/AC2: two headings differing only by an anchor disambiguator
    # (`{#fire-bolt}` / `{#fire-bolt-1}`) strip down to the same
    # `heading_path`. Numbering ordinal per section would give both
    # position 0 -- the exact duplicate citation the fix rules out.
    markdown = (
        "# Spells\n\n"
        "## Fire Bolt {#fire-bolt}\n\n"
        "A first version of this spell's description.\n\n"
        "## Fire Bolt {#fire-bolt-1}\n\n"
        "A second, differently-worded version of the same spell.\n"
    )
    chunks = service.chunk_source(_write(tmp_path, markdown))

    matching = [c for c in chunks if c.heading_path == "Spells › Fire Bolt"]
    assert len(matching) == 2
    assert sorted(c.ordinal for c in matching) == [0, 1]

    pairs = [(c.heading_path, c.ordinal) for c in chunks]
    assert len(pairs) == len(set(pairs))


def test_shipped_srd_source_yields_2132_passages_with_no_duplicate_citation():
    # <- WI1/AC2 regression: the fix must not change the real corpus's
    # shape. Reads the real, committed document (not a `tmp_path` fixture)
    # -- see the module docstring. WI3: also proves that reserving room for
    # the heading trail keeps every chunk's actually-embedded token count
    # at or under `MAX_CHUNK_TOKENS`, without needing an extra split
    # anywhere in the real document.
    path = service.SRD_ROOT / service.SOURCE_VERSION / service.SOURCE_FILENAME
    chunks = service.chunk_source(path)

    assert len(chunks) == 2132

    pairs = [(c.heading_path, c.ordinal) for c in chunks]
    assert len(pairs) == len(set(pairs))

    for chunk in chunks:
        assert chunk.token_count <= service.MAX_CHUNK_TOKENS
