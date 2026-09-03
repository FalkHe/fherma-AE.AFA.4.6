"""Tests for `app.services.ingestion.storage`.

The path shape is a contract: `source_documents.raw_path` stores exactly what
`save_raw_document` returns, and it must stay relative to DATA_DIR so the data
directory can move.
"""

from collections.abc import Callable
from pathlib import Path

from app.core.config import get_settings
from app.services.ingestion import storage

MOTORBIKE_ID = "01JZZH0K3QZ8V9W4M8F7Q2R5T1"
DOCUMENT_ID = "01JZZH0K3QZ8V9W4M8F7Q2R5T2"


def test_path_shape_is_sources_motorbike_document_html() -> None:
    assert (
        storage.raw_document_path(MOTORBIKE_ID, DOCUMENT_ID)
        == f"sources/{MOTORBIKE_ID}/{DOCUMENT_ID}.html"
    )


def test_writes_the_payload_and_returns_the_relative_path(tmp_path: Path) -> None:
    payload = b"<html><body><p>raw</p></body></html>"

    relative_path = storage.save_raw_document(MOTORBIKE_ID, DOCUMENT_ID, payload, data_dir=tmp_path)

    assert relative_path == f"sources/{MOTORBIKE_ID}/{DOCUMENT_ID}.html"
    assert not Path(relative_path).is_absolute()
    assert (tmp_path / relative_path).read_bytes() == payload


def test_creates_the_motorbike_directory_and_overwrites_the_same_document(
    tmp_path: Path,
) -> None:
    storage.save_raw_document(MOTORBIKE_ID, DOCUMENT_ID, b"first", data_dir=tmp_path)
    storage.save_raw_document(MOTORBIKE_ID, DOCUMENT_ID, b"second", data_dir=tmp_path)

    directory = tmp_path / "sources" / MOTORBIKE_ID
    assert [entry.name for entry in directory.iterdir()] == [f"{DOCUMENT_ID}.html"]
    assert (directory / f"{DOCUMENT_ID}.html").read_bytes() == b"second"


def test_defaults_to_the_configured_data_dir(
    settings_override: Callable[..., None], tmp_path: Path
) -> None:
    settings_override(DATA_DIR=tmp_path / "data")

    relative_path = storage.save_raw_document(MOTORBIKE_ID, DOCUMENT_ID, b"payload")

    assert get_settings().data_dir == tmp_path / "data"
    assert (tmp_path / "data" / relative_path).read_bytes() == b"payload"
    assert storage.resolve(relative_path) == tmp_path / "data" / relative_path
