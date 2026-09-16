---
author: fhit:architect
owner: agent
created: 2026-09-15
---
# Research: sprint 001/05 — an image call round-trips and writes a file that opens

## Facts

`openrouter` 0.10.8 (local, `uv.lock:545`) **exposes images directly** — the intent research's "no SDK support, raw
`httpx`" premise is wrong a second time, as it was for embeddings. `client.images.generate(*, model: str, prompt: str,
aspect_ratio=, n=, output_format=, quality=, resolution=, seed=, size=, stream=, …)` sits at
`site-packages/openrouter/images.py:157` and posts `path="/images"` (`:261`) against the SDK's one server
`https://openrouter.ai/api/v1` (`sdkconfiguration.py:21`,`:48`). **AC3 holds by construction**: the URL is the SDK's,
the model is ours, Google is never reached. No raw `httpx`, no `classify()` change, no adapter. Failures
(`images.py:344`-`414`) raise `openrouter.errors.*` for 400/401/402/403/404/429/500/502/524/529 and
`OpenRouterDefaultError` for any other 4XX/5XX — all `OpenRouterError` with `.status_code`, which `classify()` already
dispatches on (`app/core/llm/errors.py:208`,`:133`). AC4's eight codes come free and `call_with_retry` (`retry.py:113`)
wraps the call unchanged, as for `embed_texts` (`service.py:294`-`315`).

**Response** (`components/imagegenerationresponse.py:36`,`:17`): `created: int`, `data: list[{b64_json: str, media_type:
str|None}]`, `usage: ImageGenerationUsage|None` — base64 inside the JSON body, **no URL, no second network call, no new
failure mode**. The declared return type is a union with `EventStream` when `stream=True`
(`operations/createimages.py:137`); the seam never passes `stream`, but must still reject a
non-`ImageGenerationResponse` as `LlmMalformedError`, mirroring `service.py:247`. **Usage** has required
`prompt_tokens`/`completion_tokens`/`total_tokens` plus `cost: OptionalNullable[float]`. Trap: when absent `usage.cost`
reads back as `Unset()`, **not `None`** — unlike embeddings' plain `Optional[float]` (`operations/createembeddings.py`).
`_cost_text` (`commands.py:16`) tests `is None` first, so it would reach `round(Unset(), 6)` → `TypeError`; the seam
must coerce a non-numeric `cost` to `None`.

**One live call was made** (2026-09-15, real key, D4's `google/gemini-3.1-flash-image`): `ImageGenerationResponse`,
`created=0`, one `data` item, `media_type="image/png"` (present, though the SDK docs say it is omitted for raster
output), `b64_json` decoding to 1 737 822 bytes opening `\x89PNG\r\n\x1a\n` — a real PNG. `usage`: `prompt_tokens=12`,
`completion_tokens=1120`, `total_tokens=1132`, **`cost=0.067206`**. **D3 is satisfied: tokens and USD both return**, and
the pinned model is reachable on this path.

`Settings` has no `image_model` field (`app/core/settings.py:10`-`21`); `.env.dist:57` already sets `IMAGE_MODEL` (D4)
but `extra="ignore"` (`settings.py:9`) drops it today and `.env.dist` is owner-only, so the field is all this sprint
adds. Test seam, unchanged from sprint 04: monkeypatch `service.build_sdk_client` to an `openrouter.OpenRouter` on
`httpx.MockTransport` (`tests/core/llm/test_embeddings.py:44`-`57`); the handler gets the real `httpx.Request`, so AC3
is asserted on `request.url` and `json.loads(request.content)["model"]` — no new logging is needed *for the test*.
`tests/conftest.py:22`-`25` pins model env vars before import; `IMAGE_MODEL` must join them. For the human's live run
nothing logs a request URL today (only `retry.py:89`,`:100`), so WI1 adds one line. AC5 holds by construction:
`generate_image` returns bytes or raises, no placeholder branch exists in the seam, and the CLI is the only writer.

## Work items

- **WI1 — the seam.** `image_model` on `Settings`; `IMAGE_MODEL=test/image-model` in `tests/conftest.py`; `ImageResult`
  + `generate_image()` in `app/core/llm/service.py` per Interfaces, inside `call_with_retry(label="image")` with the
  same `_attempt()` / `classify()` / re-raise-unclassified shape as `embed_texts`; a `logger.info("llm_image_request",
  url=…, model=…)` before the call, `url` **derived** from `client.sdk_configuration.get_server_details()[0] +
  "/images"`, never a literal (AC3); tests in `backend/tests/core/llm/test_images.py` for the eight codes via
  `MockTransport`, the request URL and model, the malformed cases, and "raises, never substitutes" (AC5). One line in
  `docs/architecture.md:15`: images go direct through the OpenRouter SDK, not LangChain (← D1).
- **WI2 — the CLI.** `app llm image` in `app/core/llm/commands.py` per Interfaces, plus the `_usage_text(usage)`
  extraction; tests in `backend/tests/core/llm/test_commands_image.py` — file written byte-identical to the seam's
  bytes, the two stdout lines, overwrite, a bad `--out` parent rejected before any call, failure exit 1 with one
  line. WI1 and WI2 share no file and run in parallel; WI2 codes against Interfaces alone.

## Interfaces

`app/core/llm/service.py` — additive; no existing signature changes:
```python
@dataclass(frozen=True)
class ImageResult:
    image_bytes: bytes        # decoded from data[0].b64_json
    media_type: str           # data[0].media_type, or "image/png" when absent
    usage: Usage              # the existing dataclass, service.py:53
def generate_image(prompt: str, *, model: str | None = None) -> ImageResult: ...
```

`model` falls back to `get_settings().image_model`. Only `model=` and `prompt=` are passed to `client.images.generate` —
never `n`, `stream`, `resolution`, `aspect_ratio`, `output_format`. Raises, never returns a substitute:
`LlmConfigurationError` (blank key) and `LlmBadRequestError` (blank prompt) before any network call; the eight
`LlmError` classes via `classify()`; `LlmMalformedError` when the return is not an `ImageGenerationResponse`, when
`data` is empty, or when `b64_json` fails to decode (`binascii.Error` is otherwise unclassified and would escape as a
foreign exception). `Usage.cost_usd` is `float(usage.cost)` only when `usage.cost` is an `int`/`float`, else `None`; the
three token counts are copied as-is; `usage is None` → zeros and `cost_usd=None`, like `_usage_of_embeddings`
(`service.py:208`).

`app/core/llm/commands.py` — `app llm image "<prompt>" --out <path> [--model <id>] [--details]`. `--out` is required.
Success writes the file binary, overwriting an existing one without prompting, and prints exactly two stdout lines:
```
wrote <path> (1737822 bytes, image/png)
tokens: prompt=12 completion=1120 total=1132 · cost: $0.067206
```

Line 2 is `_usage_text(result.usage)`, where `_usage_text(usage: Usage) -> str` is lifted out of `_usage_line`
(`commands.py:23`), which becomes `_usage_text(llm_service.usage_of(message))` — `chat`'s output stays byte-identical
and `_cost_text` (`:9`) is reused untouched. An `--out` whose parent is missing or not a directory raises
`typer.BadParameter` **before** the network call (exit 2, nothing spent). An `OSError` at write time prints line 2 on
stdout first (the call was paid for), then path and reason on stderr, exit 1. `LlmError` goes through
`_report_failure(exc, details=details)` (`:32`) unchanged: one generic line, exit 1.

## Open questions

**None product-visible — the sprint is clear to start.** D3's USD requirement is met by live evidence; D1's "through
OpenRouter" ruling is honoured by the SDK's own `/api/v1/images`. *Technical, non-blocking*: ~$0.067 and ~1.7 MB per
portrait at the model's defaults — `resolution`/`output_format` exist on `images.generate` if either matters later, but
choosing them is out of scope here.
