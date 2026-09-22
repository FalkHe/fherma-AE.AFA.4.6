---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 05

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | `character/routes.py` + wire schemas (`CreationReply`, `SheetSoFar`, step enum) mounted in v1; app-state conversation map + lazily built agent; `CreationTurn.draft`, `service.creation_progress`, `take_default_equipment` writing a draft key, in-voice model-error reply moved to service; README; `tests/character/conftest.py::scripted_model` fixture; one route test per AC; then `make generate-api`, commit spec + client, `make frontend-typecheck` | AC1 start answers the greeting naming the seed hero, run with a character → 409 · AC2 one message → one whole reply · AC3 reply carries sheet, step, canSave · AC4 anonymous 401, non-member 404, model failure → 200 in-voice reply with `error` · AC5 abandoned conversation → no character row · AC6 client regenerated, lint green | – |
| qa | qa | `tests/character/test_acceptance_creation_chat.py`: black-box over the HTTP app with the `scripted_model` fixture — start, one message, the refusals | AC1, AC2, AC4 as a user of the API sees them | I1, I2 (runs once WI1 lands) |

## Interfaces
- I1: routes, payloads, status codes and the `CreationReply` / `SheetSoFar` / `step` shapes exactly as in `research.md → Interfaces`.
- I2: the `scripted_model` fixture contract in `research.md → Interfaces` (`install(*turns)`; str = Keeper words, `(tool_name, args)` = one tool call whose real tool runs, `Exception` = raised from the model call).
- Technical decisions 1–5 of the research are binding: in-memory state on `app.state`, run/user never from the client, membership re-checked per message, model failure = 200 + in-voice line + `error: true`, saving stays the agent's tool.

## Acceptance tests (qa)
- AC1 → start on a fresh run returns 201 with a greeting naming Rosalind Thorn; start on a run with a character returns 409 `CHARACTER_EXISTS`.
- AC2 → one message returns exactly one reply with the Keeper's words from the scripted model.
- AC4 → anonymous start 401; a message on an unknown conversation 404; a model exception → 200 with the in-voice line and `error: true`.

## Order
Parallel: WI1, qa (qa writes against I1/I2 and runs once WI1's fixture exists). Then gates.
