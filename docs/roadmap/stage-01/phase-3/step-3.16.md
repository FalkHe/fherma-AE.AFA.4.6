---
phase: 3
step: "3.16"
title: Scripted-conversation demo & prompt hardening
summary: A demo script driving a 6–8 turn interview over the real HTTP API with assertions on tool calls, grounded recommendations, sources, backlog flagging and resumability — plus one timeboxed prompt-tuning pass.
effort: 2
dependencies: ["3.14"]
---

# Step 3.16 — Scripted-conversation demo & prompt hardening

**Effort: 2** — one script and a timeboxed tuning loop; "plausible
interview" is the bar, not perfection.

Binding contract: `docs/roadmap/stage-01/phase-3/shared-knowledge.md`. Agent:
**backend-dev**.

## Outline

- `backend/scripts/demo_conversation.py`: register/login over HTTP (cookie
  jar + `X-CSRF-Token` header), create a chat (assert the advisor's
  greeting arrives first, before any scripted turn), run a 6–8 turn
  scripted interview against the real API (worker up), polling
  `chat-messages` for each reply. Asserts: ≥3 **distinct** tool calls
  occurred across the
  conversation; recommendations reference approved models only; sources
  attached where knowledge was retrieved; a deliberately mentioned
  uncatalogued bike created exactly one backlog row; re-fetching the chat
  reproduces the full history (resumability = persistence).
- One prompt-tuning pass on `advisor_system.md`, timeboxed to the remaining
  session — adjust stage ordering/steering only; schema and loop are frozen.
- The script is the phase's repeatable evidence generator (3.17 and Phase
  5.3 reuse it).

## Verification

- `docker compose exec app-web python scripts/demo_conversation.py` prints
  the transcript and every assertion passes.

## Risks / notes

- The script hits live OpenRouter — flaky turns should retry once before
  failing the run, and the script must clean up its throwaway user/chat and
  the flagged backlog row (leave the deliverable DB as found).
- If interview quality disappoints, the intended knob is `CHAT_MODEL` in
  `.env` (owner decision, see `open-questions.md`) — not code changes.
