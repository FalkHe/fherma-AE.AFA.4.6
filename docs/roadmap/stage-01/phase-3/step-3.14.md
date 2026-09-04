---
phase: 3
step: "3.14"
title: Preference capture & unknown-bike flagging
summary: The record_preference tool (firmness-tagged capture with supersession, injected into every context rebuild) and the flag_unknown_bike tool (idempotent backlog insert) — the two remaining permitted autonomous writes.
effort: 3
dependencies: ["3.13", "2.1"]
---

# Step 3.14 — Preference capture & unknown-bike flagging

**Effort: 3** — two thin tools over services that already exist (3.1's
preference functions, 2.1's `create_backlog`), plus the prompt block wiring.

Binding contract: `docs/roadmap/stage-01/phase-3/shared-knowledge.md` (§Agent-loop
decisions — write-tool policy, §Tool result schemas). Agent: **backend-dev**.

## Outline

- `tools/record_preference.py` (args: `attribute`, `value`,
  `firmness ∈ hard|soft|exploring`) → `chat_service.record_preference`
  (3.1's supersession); result = the pinned ack shape. Active preferences
  are injected into the system prompt on every context rebuild (verify the
  3.13 block actually renders them — this step owns the end-to-end proof).
- `tools/flag_unknown_bike.py` → `product_service.create_backlog`, catching
  `DuplicateModelError` for dedup across **all** statuses (idempotent:
  repeated mentions = one row); result = the pinned
  `{"name", "status": "queued"|"already_known"}` shape. Wire the resolver's
  `unknownBike` outcome into the prompt guidance ("offer to note it for
  research").
- Both registered in `build_advisor_tools`; both persisted in `tool_calls`
  like every call (the UI renders them as subtle rows, ui-spec §8.7).
- These are the explicitly permitted low-risk autonomous writes
  (shared-knowledge pins the policy) — no confirmation flow, no additional
  write tools.
- Tests: supersession end-to-end through the tool, flag idempotency on
  name/slug (existing catalogue name, existing backlog name, double
  mention), prompt block contains the active preferences after a capture.

## Verification

- In a curl conversation: stating "budget around 6000 €" then "actually max
  5000 €" leaves one active + one superseded preference row; mentioning an
  uncatalogued bike leaves exactly one `backlog` row visible in the admin
  backlog UI; repeating the mention adds none. **This closes milestone M4's
  backend half.**

## Risks / notes

- Dedup must run against all statuses, not just `backlog` — an approved
  model mentioned by name must return `already_known`, not a duplicate row.
