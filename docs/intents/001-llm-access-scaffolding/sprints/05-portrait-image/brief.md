---
author: intake
owner: human
created: 2026-09-15
stage: approved
---
# Sprint 05: an image call round-trips and writes a file that opens

## Outcome
`app llm image "<prompt>" --out <file>` writes a portrait that opens as an
image, and prints that call's USD cost.

## Acceptance criteria
- AC1: with a real key, the command writes the named file and it opens as an image in a normal viewer.
- AC2: the same run prints the call's USD cost.
- AC3: the request goes to OpenRouter's `/api/v1/images` with `IMAGE_MODEL`, never to Google's own API — verifiable from the logged request URL.
- AC4: the gateway failures of sprint 02 raise the same eight codes here — asserted without a key.
- AC5: the seam raises on failure and never substitutes a placeholder itself; choosing a fallback is the caller's business.

## Decisions
← D1, D3, D4

## Assumptions
- `generate_image(...) -> bytes + content type`; writing the file is the CLI's job, not the seam's.
- The response's base64 payload is decoded in the seam; resolution and aspect ratio take defaults for now.
- `IMAGE_MODEL=google/gemini-3.1-flash-image` is already in `.env.dist` (D4); this sprint adds nothing there.

## Out of scope
The deterministic placeholder portrait and the character-creation flow around it
(phase 7) · storing portraits anywhere · letting anyone pick resolution or style.
