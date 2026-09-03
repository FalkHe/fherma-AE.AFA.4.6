"""QA coverage for `app.services.ingestion.storage` — path-traversal risk.

`raw_document_path` builds `sources/{motorbike_id}/{document_id}.html` with plain
string interpolation via `PurePosixPath`, which does **not** normalize `..`
segments. `motorbike_id`/`document_id` are ULIDs minted by our own services in
every real call site, but this module has no boundary of its own that rejects a
hostile id — so it is worth proving, precisely, what currently happens if one
ever reaches it. These tests document the *actual* behaviour (they are not
assertions that the behaviour is desired); see the QA report for the finding.
"""

from pathlib import Path

from app.services.ingestion import storage

DOCUMENT_ID = "01JZZH0K3QZ8V9W4M8F7Q2R5T2"


def test_a_traversal_motorbike_id_escapes_the_sources_subdirectory(tmp_path: Path) -> None:
    """`motorbike_id="../evil"` writes outside `sources/`, still inside DATA_DIR.

    FINDING: `sources/../evil/{document_id}.html` collapses (once joined to a
    real filesystem path) to `DATA_DIR/evil/{document_id}.html` — the payload is
    no longer under the `sources/` tree the rest of the contract assumes.
    """
    relative_path = storage.save_raw_document("../evil", DOCUMENT_ID, b"payload", data_dir=tmp_path)

    written_at = (tmp_path / relative_path).resolve()

    assert written_at == (tmp_path / "evil" / f"{DOCUMENT_ID}.html").resolve()
    assert not written_at.is_relative_to((tmp_path / "sources").resolve())
    assert written_at.is_relative_to(tmp_path.resolve())  # still inside DATA_DIR, here


def test_a_deeper_traversal_motorbike_id_escapes_data_dir_entirely(tmp_path: Path) -> None:
    """`motorbike_id="../../evil"` writes a file outside DATA_DIR altogether.

    FINDING (security): with enough `../` segments, `save_raw_document` writes
    to any path the process has permission for — a full path-traversal
    vulnerability if `motorbike_id`/`document_id` were ever attacker-controlled.
    Not exploitable via the current API (ids are server-minted ULIDs before this
    function is called), but there is no defence inside `storage.py` itself.
    """
    relative_path = storage.save_raw_document(
        "../../escaped", DOCUMENT_ID, b"payload", data_dir=tmp_path
    )

    written_at = (tmp_path / relative_path).resolve()

    assert not written_at.is_relative_to(tmp_path.resolve())
    assert written_at == (tmp_path.parent / "escaped" / f"{DOCUMENT_ID}.html").resolve()
    written_at.unlink()  # tidy up: this landed outside tmp_path's own cleanup.
    written_at.parent.rmdir()


def test_a_traversal_document_id_escapes_the_motorbike_directory(tmp_path: Path) -> None:
    """The same lack of normalization applies to `document_id`."""
    relative_path = storage.save_raw_document(
        "bike123", "../escaped-doc", b"payload", data_dir=tmp_path
    )

    written_at = (tmp_path / relative_path).resolve()

    assert written_at == (tmp_path / "sources" / "escaped-doc.html").resolve()
    assert not written_at.is_relative_to((tmp_path / "sources" / "bike123").resolve())
