"""qa acceptance tests -- sprint 004/02 "fetch and chunk" (AC1-AC6),
`docs/intents/004-srd-knowledge-base/sprints/02-fetch-and-chunk/brief.md`.

Black-box throughout: AC1, AC2, AC3 and AC5 drive the real `app srd ingest
--dry-run` command through `typer.testing.CliRunner` against `app.cli.cli`.
The network is never touched: `httpx.get` is the module-level seam the
fetch goes through (`research.md`, "the same shape works here via a
module-level `httpx.get`" -- the same idiom `service.build_sdk_client` uses
elsewhere in this codebase), so tests monkeypatch the real `httpx.get`
function for the duration of one test; because `httpx` is a single shared
module object, this reaches the call inside `service.py` regardless of how
it imported the name. `SRD_ROOT` is repointed to `tmp_path` via
`monkeypatch.setattr(srd_service, "SRD_ROOT", ...)`, mirroring the
`CONTENT_ROOT` precedent in `tests/content/conftest.py` -- never a rebound
import, which would make the monkeypatch silently miss. AC4 calls
`chunk_source` directly against a fixture file of known shape; no network
or CLI involved. AC6 reads the real, unmocked shipped tree and the real
repository `README.md` -- no monkeypatch, no fixture.

No `pytest-asyncio` (`AGENTS.md` gotchas): every call here is synchronous,
so no `asyncio.run` is needed in this file.
"""

from pathlib import Path

import httpx
from typer.testing import CliRunner

from app.cli import cli
from app.modules.srd import service as srd_service

runner = CliRunner()

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

# A small, fully-controlled fixture document -- never the real ~1.9 MB
# corpus. Three headed sections, one of them nested three deep, giving the
# exact heading-path shape the brief's AC2 example uses.
FIXTURE_MARKDOWN = (
    b"# Combat\n\n"
    b"## Cover\n\n"
    b"### Half Cover\n\n"
    b"You have half cover if an obstacle blocks at least half of your body.\n\n"
    b"## Another Rule\n\n"
    b"Short filler text for another rule under combat.\n\n"
    b"# Exploration\n\n"
    b"## Traps\n\n"
    b"Simple filler text about traps in dungeons.\n"
)


def _fake_get(body: bytes, *, status_code: int = 200):
    """A stand-in for `httpx.get` returning a real `httpx.Response` -- so
    whatever `fetch_source` does with it (`.status_code`, `.content`,
    `.text`, `.raise_for_status()`) works exactly as it would against a
    live server, without a socket ever opening."""

    def _get(url, *args, **kwargs):
        return httpx.Response(status_code, content=body, request=httpx.Request("GET", url))

    return _get


def _expected_path(tmp_path: Path) -> Path:
    return tmp_path / srd_service.SOURCE_VERSION / srd_service.SOURCE_FILENAME


def test_ac1_dry_run_writes_the_stored_file_and_prints_path_and_byte_count(tmp_path, monkeypatch):
    # <- AC1
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    monkeypatch.setattr(httpx, "get", _fake_get(FIXTURE_MARKDOWN))

    result = runner.invoke(cli, ["srd", "ingest", "--dry-run"])

    assert result.exit_code == 0, result.output
    expected_path = _expected_path(tmp_path)
    assert expected_path.read_bytes() == FIXTURE_MARKDOWN
    assert str(expected_path) in result.stdout
    assert str(len(FIXTURE_MARKDOWN)) in result.stdout


def test_ac2_dry_run_prints_chunk_count_token_count_and_a_sample_heading_path(
    tmp_path, monkeypatch
):
    # <- AC2
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    monkeypatch.setattr(httpx, "get", _fake_get(FIXTURE_MARKDOWN))

    result = runner.invoke(cli, ["srd", "ingest", "--dry-run"])
    assert result.exit_code == 0, result.output

    # Compute the expected numbers through the same public contract the
    # command itself is built on, against the file the command just wrote --
    # never hand-guessed constants tied to a particular splitting algorithm.
    chunks = srd_service.chunk_source(_expected_path(tmp_path))
    expected_chunk_count = len(chunks)
    expected_token_total = sum(chunk.token_count for chunk in chunks)

    assert str(expected_chunk_count) in result.stdout
    assert str(expected_token_total) in result.stdout
    # A reference good enough to cite (<- D4), in the exact joined shape the
    # brief's own example uses.
    assert "Combat › Cover › Half Cover" in result.stdout


def test_ac3_reingest_overwrites_the_stored_file_in_place(tmp_path, monkeypatch):
    # <- AC3. The "unchanged upstream leaves the tree clean" half needs a
    # real network fetch of the real committed file to observe `git diff`
    # staying empty -- unreachable without touching the network, so this
    # test asserts only the overwrite-in-place half: same path, new bytes,
    # no second file appears.
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)

    monkeypatch.setattr(httpx, "get", _fake_get(FIXTURE_MARKDOWN))
    first = runner.invoke(cli, ["srd", "ingest", "--dry-run"])
    assert first.exit_code == 0, first.output

    changed_markdown = FIXTURE_MARKDOWN + b"\n## A New Rule\n\nSomething the upstream added.\n"
    monkeypatch.setattr(httpx, "get", _fake_get(changed_markdown))
    second = runner.invoke(cli, ["srd", "ingest", "--dry-run"])
    assert second.exit_code == 0, second.output

    expected_path = _expected_path(tmp_path)
    assert expected_path.read_bytes() == changed_markdown

    version_dir = tmp_path / srd_service.SOURCE_VERSION
    assert [p.name for p in version_dir.iterdir()] == [srd_service.SOURCE_FILENAME]


def test_ac4_an_oversized_section_splits_with_overlap_keeping_its_heading_path(tmp_path):
    # <- AC4. `MAX_CHUNK_TOKENS` (800) is the cap that is actually enforced
    # -- well under `EMBEDDING_WINDOW_TOKENS` (8192) precisely so a fixture
    # section can be built large enough to force a real split while still
    # respecting the window too.
    body = " ".join(f"tok{i:05d}" for i in range(5000))
    fixture = f"# Combat\n\n## Cover\n\n### Half Cover\n\n{body}\n".encode()
    path = tmp_path / "fixture.md"
    path.write_bytes(fixture)

    heading_path = "Combat › Cover › Half Cover"
    chunks = [c for c in srd_service.chunk_source(path) if c.heading_path == heading_path]
    chunks.sort(key=lambda c: c.ordinal)

    assert len(chunks) >= 2, "fixture section must force at least one split"
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert all(c.heading_path == heading_path for c in chunks)

    for chunk in chunks:
        assert chunk.token_count <= srd_service.MAX_CHUNK_TOKENS
        assert chunk.token_count <= srd_service.EMBEDDING_WINDOW_TOKENS

    # Overlap: the tail of each chunk's text reappears at the head of the
    # next one -- both are decoded from the same contiguous span of the
    # original token stream, so this is a plain substring check.
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        probe = earlier.text[-30:]
        assert probe in later.text, (probe, later.text[:60])


def test_ac5_unreachable_source_exits_nonzero_with_no_traceback_and_leaves_file_untouched(
    tmp_path, monkeypatch
):
    # <- AC5
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    expected_path = _expected_path(tmp_path)
    expected_path.parent.mkdir(parents=True)
    original_bytes = b"# Combat\n\nprevious ingest's stored content\n"
    expected_path.write_bytes(original_bytes)

    def _raise_get(url, *args, **kwargs):
        raise httpx.ConnectError("Name or service not known")

    monkeypatch.setattr(httpx, "get", _raise_get)

    result = runner.invoke(cli, ["srd", "ingest", "--dry-run"])

    assert result.exit_code != 0
    assert "Traceback" not in result.output
    stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1, result.stderr
    assert expected_path.read_bytes() == original_bytes


def test_ac6_license_file_and_readme_state_the_cc_by_attribution():
    # <- AC6. Unmocked: reads the real shipped tree and the real repository
    # README, never a fixture.
    license_text = (srd_service.SRD_ROOT / srd_service.SOURCE_VERSION / "LICENSE.md").read_text()
    readme_text = (REPO_ROOT / "README.md").read_text()

    for text in (license_text, readme_text):
        assert "System Reference Document 5.1" in text
        assert "Wizards of the Coast" in text
        assert "Creative Commons Attribution 4.0" in text
        assert "creativecommons.org/licenses/by/4.0" in text
