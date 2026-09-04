---
phase: 5
step: "5.9"
title: Langfuse callback factory
summary: Add the langfuse dependency and the three LANGFUSE_* config keys; observability_callbacks returns the LangChain handler iff all three are set, else []. Chat-model paths only (embeddings excluded); a Langfuse outage never fails an LLM call. Opens with a compat spike.
effort: 3
dependencies: ["5.6"]
---

# Step 5.9 — Langfuse callback factory

**Effort: 3** — the code slot already exists (`observability_callbacks`
returns `[]` with a docstring naming this step); the effort is the compat
spike, the dependency/config plumbing, and the failure-isolation proof.

Binding contract: `docs/roadmap/stage-01/phase-5/shared-knowledge.md` (D5; hard
rules — this step owns the phase's **only** new dependency and **only**
three new config keys). Agent: **backend-dev**. Zero deviations — a
deviation is a stop-and-report.

**Environment:** stack up for the live checks; **restart `app-worker` after
landing**; run `make build` after the dependency change (CLI images).

## Outline

1. **Compat spike first** (before any plumbing): in the app-cli container,
   `uv add langfuse` on a scratch branch and verify the LangChain callback
   handler (langfuse v3: `from langfuse.langchain import CallbackHandler` —
   verify the actual import path) constructs and traces against the
   installed `langchain 1.3.17` / `langchain-core 1.6.0`. If incompatible,
   **stop and report to the coordinator** — the owner has pre-authorized
   dropping Langfuse entirely on any friction (D5, resolved OQ-B/OQ-C);
   spend no effort on fallbacks.
2. `backend/pyproject.toml` + `uv.lock`: add `langfuse` (pin the major).
3. `backend/app/core/config.py` + `.env.dist` (lockstep):
   `langfuse_public_key: str = ""`, `langfuse_secret_key: str = ""`,
   `langfuse_host: str = ""` — commented as optional in `.env.dist`.
4. `backend/app/llm/models.py` `observability_callbacks(settings)`: return
   `[CallbackHandler(...)]` iff all three are non-empty, else `[]`. The
   chat-model call sites already consume the factory — **no call-site
   changes**. Embeddings stay out (D5 — LangChain embeddings emit no
   callback events; documented limitation).
5. Failure isolation: handler construction/flush errors must never
   propagate into a chat turn — verify langfuse's handler swallows/logs its
   own transport errors; if it doesn't, wrap the handler creation and rely
   on the SDK's background queue semantics; a *raising* handler is a
   stop-and-report.
6. Tests: rewrite
   `tests/llm/test_models.py::test_no_callbacks_until_langfuse_is_wired` →
   asserts `[]` without keys and one handler with all three keys set
   (monkeypatched settings; no network). The only permitted pytest-config
   change is a `filterwarnings` ignore scoped to langfuse deprecation
   warnings, and only if the suite forces it.

## Verification

- `make build && make backend-test && make backend-lint` green.
- With keys unset: behaviour byte-identical (spot-check one chat turn).
- With a **wrong** `LANGFUSE_HOST` set: a live chat still completes
  (failure isolation proven).
- Full-trace proof (agent steps + tool calls visible in a Langfuse UI)
  belongs to 5.10's/M2's demo — here a cloud instance may be used if handy,
  but is not required.

## Risks / notes

- `filterwarnings = ["error"]` is active — a noisy SDK will surface
  immediately; scope any ignore to the exact warning.
- 5.6 edits the same file — this step depends on it (in-track order).
- Append (`### Step 5.9`) to `shared-knowledge.md`: exact import path,
  handler construction kwargs, and any filterwarnings entry — 5.10 and the
  docs steps build on them.
