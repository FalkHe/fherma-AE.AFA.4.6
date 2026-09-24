---
author: sprint
owner: agent
created: 2026-09-24
---
# Plan: Sprint 06

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 3 | backend-python | One shared way to build the storyteller model through the existing access seam and to read a call's token usage into the flow's usage type (I0) | usage summed from a scripted response; model built through the seam only | – |
| 1 | backend-python | Six narrow decision strategies with their own prompt, structured output shape, allowed operations and evidence view (I1); a decision whose output names an unsupported operation or something not in the scene is rejected and retried within a fixed budget; rules lookup and history recall are bound as read-only tools only to the strategies that need them, capped at three calls per decision | unknown operation rejected then raised after the budget; out-of-scene reference rejected; tool loop stops at three calls | I0 |
| 2 | backend-python | A separate, tool-free narration call that turns the public situation and allowed evidence into a draft, plus the state rule that the draft stays until recording succeeds (I2) | narration input has no hidden fact, difficulty or private intent and the model has no tools bound; the draft survives in state until record_beat reports ok | I0 |

## Interfaces
- I0 `agent/model_call.py`: `build_model() -> BaseChatModel` (via `core/llm` `chat_model()`); `to_usage(messages) -> flow_state.Usage`; `async ainvoke(runnable, messages, *, label) -> AIMessage`.
- I1 `agent/decisions.py` (+ `prompts/v1/decision/*.md`): `DecisionKind` StrEnum {read_move, interpret_evidence, judge_reference, assess_move, monster_action, world_reaction}; `DecisionRequest(decision_id, kind, evidence_ids, payload)`; `DecisionResult(decision_id, kind, value, usage)`; per-kind value dataclasses `ReadMoveDecision(intent, refs, proposed: tuple[OperationSpec,...] | None)`, `EvidenceReading(summary, supports)`, `ReferenceJudgement(chosen_id | None, ask_choice)`, `MoveAssessment(applies, dc, dc_source authored|rules, consequence_ids)`, `MonsterAction(actor_id, attack, target_id)`, `WorldReaction(reactions)`; `Strategy(prompt_key, output_schema: type[BaseModel], allowed_operations: frozenset[OperationKind], binds_tools: bool, evidence, build)`; `DECISION_HANDLERS: dict[DecisionKind, Strategy]`; `DecisionContext(db, user_id, run_id, hero_id, situation, model)`; `MAX_TOOL_CALLS = 3`; `RETRY_BUDGET = 2`; `DecisionInvalid`; `async decide(ctx, request, state) -> DecisionResult`. Validation: every proposed `OperationSpec.kind` in `allowed_operations`, every id through `operations.validate_refs`; failure re-prompts with the reason under the same decision id, then raises. Pydantic only for the output schemas.
- I2 `agent/narration.py` (+ `prompts/v1/narration/beat.md`): `BeatKind = Literal["opening","attempt","outcome","answer","arrival","refusal","closing"]`; `BeatRequest(beat_id, kind, allowed_evidence_ids, payload)`; `BeatDraft(beat_id, text, usage)`; `async narrate(ctx: DecisionContext, request, state) -> BeatDraft` from `situation.public()` and the allowed evidence, no tools bound; `draft_state(draft) -> StateDelta` and `recorded_state(beat_id, event_id) -> StateDelta` for the narrative cursor.
- Structured output via `with_structured_output(..., include_raw=True)` so usage is kept; a scripted fake chat model in tests supports tool calls and structured output.

## Acceptance tests (qa)
No qa agent (owner: reduce testing); WI tests cover AC1–AC4.

## Order
WI3 first (minutes). Then parallel: WI1, WI2.
