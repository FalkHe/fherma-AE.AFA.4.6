---
phase: 2
step: "2.12"
title: Image pipeline (Pillow variants, /media)
summary: image_service — download one image, generate the pinned WebP variant set (thumb 320 / card 640 / detail 1280) into MEDIA_DIR, create the pending motorbike_images row — plus the StaticFiles mount at /media.
effort: 3
dependencies: ["2.1", "2.10"]
agent: backend-dev
track: backend
---

# Step 2.12 — Image pipeline (Pillow variants, `/media`)

**Effort: 3** — one service, one static mount, one dev command.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *DB schema →
motorbike_images* (deterministic variant path formula — 2.9 computes URLs
from it, so the formula is a contract), *Ingestion decisions* (variant
sizes/format/quality, media dir). Zero deviations; stop and report if one
seems necessary.

## Files

- Create `backend/app/services/image_service.py`
- Create `backend/tests/services/test_image_service.py`
- Modify `backend/app/main.py` (StaticFiles at `/media` serving
  `MEDIA_DIR`), `backend/app/core/config.py`, `.env.dist` (`MEDIA_DIR`),
  `backend/pyproject.toml` + `uv.lock` (`pillow`),
  `backend/app/cli/ingest.py` (`fetch-image` dev command)

## Implementation outline

- `image_service.ingest_image(session, motorbike_id, image_url,
  attribution)`: download via the 2.10 fetch layer (image content-types
  allowed here), store the original under
  `MEDIA_DIR/motorbikes/{motorbike_id}/`, generate the three WebP variants
  (quality 80, aspect preserved, width-capped 320/640/1280) at the pinned
  paths, create the `pending` row. At most **one image row per ingestion
  run** (pinned).
- Non-image or failed download = typed warning result (ingestion treats a
  missing image as a warning, never a failure).
- `/media` StaticFiles mount — plain endpoint, outside auth (product images
  are public per architecture).
- Tests: tiny fixture image; variant files exist at the exact pinned paths
  with correct max widths. Run `make build` after the dependency change.

## Verification

- `make backend-test` green. Manual: `app ingest fetch-image <url> <bike-id>`
  → 3 WebP files on disk at the pinned paths;
  `curl http://localhost:8000/media/motorbikes/<id>/<imageId>_thumb.webp` →
  200.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
