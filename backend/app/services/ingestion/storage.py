"""Retaining the original payload behind every source document.

`source_documents.content_markdown` is derived data: extraction improves, models
change, and the admin needs to be able to see what a page actually said. So the
fetched bytes are kept forever under
`DATA_DIR/sources/{motorbike_id}/{document_id}.html`, and the database stores the
**DATA_DIR-relative** path — so moving or remounting the data directory never
invalidates a row.
"""

import logging
from pathlib import Path, PurePosixPath

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Sub-tree of DATA_DIR holding retained source payloads.
SOURCES_DIRECTORY = "sources"

RAW_SUFFIX = ".html"


def raw_document_path(motorbike_id: str, document_id: str) -> str:
    """Return the DATA_DIR-relative path of one document's raw payload.

    This is the single definition of the layout: `source_documents.raw_path`
    stores exactly this string.
    """
    return str(PurePosixPath(SOURCES_DIRECTORY, motorbike_id, document_id + RAW_SUFFIX))


def resolve(relative_path: str, *, data_dir: Path | None = None) -> Path:
    """Turn a stored `raw_path` back into an absolute path under DATA_DIR."""
    return _data_dir(data_dir) / relative_path


def save_raw_document(
    motorbike_id: str,
    document_id: str,
    payload: bytes,
    *,
    data_dir: Path | None = None,
) -> str:
    """Write `payload` to its place under DATA_DIR and return the stored path.

    Args:
        motorbike_id: Owning catalogue entry — one directory per model.
        document_id: The `source_documents` row id, so the payload is findable
            from the row and re-ingestion cannot collide with an older run.
        payload: The fetched bytes, unmodified.
        data_dir: Override the configured DATA_DIR (tests, one-off tooling).

    Returns:
        The DATA_DIR-relative path to store in `source_documents.raw_path`.
    """
    relative_path = raw_document_path(motorbike_id, document_id)
    target = resolve(relative_path, data_dir=data_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    logger.info("Retained %d bytes of raw payload at %s.", len(payload), relative_path)
    return relative_path


def _data_dir(override: Path | None) -> Path:
    """The data root: the explicit override, else the configured DATA_DIR."""
    return override if override is not None else get_settings().data_dir
