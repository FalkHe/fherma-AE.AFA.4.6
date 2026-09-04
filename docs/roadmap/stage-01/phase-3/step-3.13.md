---
phase: 3
step: "3.13"
title: Advisor agent loop
summary: The tool-calling advisor — full interview system prompt, hand-rolled bind_tools loop over the four domain tools plus retrieve_bike_knowledge and present_recommendations, step/time limits, and persisted tool_calls/sources/recommendations — rewiring the responder seam.
effort: 4
dependencies: ["3.5", "3.9", "3.12"]
---

# Step 3.13 — Advisor agent loop

**Effort: 4** — the loop, the capture collector, the full system prompt, and
the rewire of `chat_response_service.generate`; the job and API never
change.

Binding contract: `docs/roadmap/stage-01/phase-3/shared-knowledge.md` (§Agent-loop
decisions, §Persisted JSONB shapes, §Tool result schemas). Agent:
**backend-dev**.

## Outline

- `backend/app/llm/prompts/advisor_system.md` full version: greeting +
  opening interview question when the history is empty (kept from 3.5),
  interview stages (experience → licence → use case → budget → physique →
  preferences), steer-but-allow-free-form, cite-sources instruction,
  out-of-domain refusal (the domain security measure), retrieved
  chunks/tool results framed as **untrusted data** (baseline hygiene; full
  sweep in 5.1), active preferences as a structured block.
- `backend/app/llm/agents/advisor.py`: **hand-rolled plain tool loop over
  `ChatOpenRouter.bind_tools(tools)`**, model =
  `get_chat_model(settings.advisor_model)` (never `CHAT_MODEL`, never a
  hardcoded id) — no LangGraph, no prebuilt executor. `run_advisor_turn(session, chat, *, model=None) ->
  AdvisorResult(body, tool_calls, sources, recommendations)`. Loop:
  system + full-history replay (body only, no past tool traffic) →
  `ainvoke` → execute tool calls sequentially, append `ToolMessage`s,
  re-invoke; at `settings.agent_max_tool_steps` one final invoke with tools
  unbound; `asyncio.timeout(settings.agent_timeout_seconds)` around the
  turn.
- Tools: the four domain tools + `retrieve_bike_knowledge` (wraps
  `rag_pipeline_service.retrieve`; contributes its chunks to `sources` —
  deduped by `sourceDocumentId`, best score, cap 8) +
  `present_recommendations` (args resolved against approved models,
  enriched into the pinned snapshot shape incl. `imageUrl`/`keySpecs`,
  stored; returns a short ack to the model). The collector records **every**
  executed call into the pinned `tool_calls` shape; a tool exception
  becomes a `failed` entry with `error`, never a crashed turn.
- Rewire `chat_response_service.generate` internals to
  `run_advisor_turn` and persist the parts via the existing
  `append_assistant_message`. Config keys land here:
  `AGENT_MAX_TOOL_STEPS=8`, `AGENT_TIMEOUT_SECONDS=120` (replace 3.5's
  interim healing constant with the settings-derived value).
- Tests (mocked model throughout): loop terminates at max steps, tool error
  → failed tool_call entry, sources dedup/cap, recommendations enrichment
  (unknown name skipped, approved-only), context rebuild injects active
  preferences.

## Verification

- Curl an interview-ish message → the persisted assistant row shows ≥1
  `toolCalls` entry with a result matching the pinned shapes, and non-empty
  `sources` when knowledge was retrieved; timeout and step-cap paths produce
  the apologetic message + failed operation, never a hung typing state.

## Risks / notes

- Interview quality is prompt work with a long tail — get it plausible, not
  perfect; the tuning timebox is 3.16.
- Full history replay is the pinned context strategy; add a rolling summary
  only if token limits actually bite (stop and report first).
