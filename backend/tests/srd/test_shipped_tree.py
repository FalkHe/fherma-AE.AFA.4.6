"""Unmocked tests over the real, shipped `backend/content/srd/v1/` tree.

Proves the SRD 5.1 rules document and its CC-BY-4.0 licence file ship in the
repository, that the licence file carries the attribution sentence and
licence URL the brief requires, and that the repository `README.md` states
the attribution too (WI4, ← AC6/D6).

Engine-free, no network: reads only the committed files.
"""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
SRD_V1 = BACKEND_ROOT / "content" / "srd" / "v1"

LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/legalcode"
ATTRIBUTION_SENTENCE_FRAGMENT = (
    "This work includes material taken from the System Reference Document 5.1"
)


def test_srd_document_ships_in_the_tree():
    document = SRD_V1 / "SRD_CC_v5.1.md"

    assert document.is_file()

    # Not asserting the full 1.9 MB content -- just that it is the real
    # document (its opening legal notice, D&D SRD prose) and not a stub.
    text = document.read_text(encoding="utf-8")
    assert len(text) > 1_000_000
    assert "System Reference Document 5.1" in text
    assert "Wizards of the Coast" in text


def test_license_file_ships_in_the_tree():
    assert (SRD_V1 / "LICENSE.md").is_file()


def test_license_file_holds_the_cc_by_attribution_sentence_and_url():
    text = (SRD_V1 / "LICENSE.md").read_text(encoding="utf-8")

    assert ATTRIBUTION_SENTENCE_FRAGMENT in text
    assert "Wizards of the Coast LLC" in text
    assert "Creative Commons Attribution 4.0 International" in text
    assert LICENSE_URL in text


def test_root_readme_states_the_attribution():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert ATTRIBUTION_SENTENCE_FRAGMENT in text
    assert "Wizards of the Coast LLC" in text
    assert LICENSE_URL in text
