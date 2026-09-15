---
author: sprint
owner: agent
created: 2026-09-15
---
# Plan: Sprint 05 — an image call round-trips and writes a file that opens

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | A seam function returning portrait bytes, its media type, and what the call cost | blank key and blank prompt refuse before any call; the eight codes raised here too; malformed shapes refuse; the request URL and model are logged and assertable; never substitutes a placeholder | I1 |
| 2 | backend-python | `app llm image` writes the file and prints what it cost | the written bytes match the seam's exactly; a bad `--out` parent is rejected before spending; an existing file is overwritten; a write failure still reports the cost | I2 |
| qa | qa | Black-box acceptance tests for AC3–AC5 | all through the sprint-02 mock seam, no API key | I1, I2 |

## Interfaces
Verbatim from `research.md → Interfaces`; binding. Summarised — read that file for the full text.

- I1: `service.py`, additive only — frozen `ImageResult(image_bytes: bytes, media_type: str, usage: Usage)` and `generate_image(prompt: str, *, model: str | None = None) -> ImageResult`. Calls `client.images.generate` passing **only** `model=` and `prompt=` — never `n`, `stream`, `resolution`, `aspect_ratio` or `output_format`. Same `_attempt()` / `classify()` / re-raise shape as `embed_texts`, inside `call_with_retry(label="image")`. Raises `LlmConfigurationError` (blank key) and `LlmBadRequestError` (blank prompt) before any network call; `LlmMalformedError` when the response is the wrong type, `data` is empty, or `b64_json` fails to decode. Logs `llm_image_request` with the URL **derived** from `client.sdk_configuration.get_server_details()[0] + "/images"`, never a literal — that is what makes AC3 assertable.
- I2: `commands.py` — `app llm image "<prompt>" --out <path> [--model] [--details]`, `--out` required. Two stdout lines: `wrote <path> (<n> bytes, <media_type>)` then the usage line. Extract `_usage_text(usage)` from `_usage_line`, leaving `chat`'s output byte-identical and reusing `_cost_text` untouched. A missing or non-directory `--out` parent raises `typer.BadParameter` **before** the call, so nothing is spent. An `OSError` at write time prints the usage line first — the call was already paid for — then the reason on stderr, exit 1.

## Acceptance tests (qa)
- AC1/AC2 → hand-run with a real key; no automated test.
- AC3 → the logged request URL ends in `/api/v1/images` and carries `IMAGE_MODEL`; never a Google host.
- AC4 → the eight sprint-02 codes raised on this path too, with exact request counts (retryable vs not).
- AC5 → every failure raises; nothing in the seam returns a placeholder, and the CLI writes no file on failure.

## Order
WI1 and WI2 share no file and run in parallel with qa; WI2 codes against I2 alone.

**Three things the research established, two of which overturn earlier assumptions:**
1. **The intent research was wrong a third time.** It assumed `/api/v1/images` needed a raw `httpx` call with no SDK support — which would have forced a `classify()` change or an adapter. `openrouter` 0.10.8 ships `client.images.generate(...)`, raising the same `OpenRouterError` types, so AC3 and AC4 hold by construction and no file three sprints depend on gets touched.
2. **D3 is satisfied by live evidence.** One real call returned a base64 PNG plus `usage` of 12/1120/1132 tokens and `cost=0.067206`.
3. **Trap:** an absent `usage.cost` reads back as `Unset()`, not `None`, which would crash `_cost_text` at `round(Unset(), 6)`. Hence cost is taken only when it is an `int`/`float`.
