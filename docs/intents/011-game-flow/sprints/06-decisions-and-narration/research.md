---
author: fhit:architect
owner: agent
created: 2026-09-24
---
# Research: sprint 011/06 — decisions and narration

## Facts

- Model seam: `chat_model(*, model, temperature) -> BaseChatModel` at `backend/app/core/llm/service.py:126`; `ainvoke_chat(runnable, prompt, label=)` (`service.py:198`) awaits an already-built/bound runnable with retry + error translation and no tracing span. New code builds once via `chat_model()` and awaits through `ainvoke_chat` — never `model.ainvoke` directly.
- Structured output is available: `ChatOpenRouter.with_structured_output(schema, *, method='function_calling'|'json_schema', include_raw=False, strict=None)` — verified in the container (langchain-core 1.6.3, langchain 1.4.2, langchain-openrouter 0.2.8, `backend/uv.lock:446,460,481` — source: local installed package). It returns a `Runnable` whose output is a parsed object, so `usage_of()` cannot read tokens off it; use `include_raw=True` and read usage from `result["raw"]`, or bind tools yourself and parse the last message. Schema must be a Pydantic model or JSON-schema dict — this is the one place Pydantic is allowed.
- Tool binding: `model.bind_tools(TOOLS)` as at `backend/app/modules/game/agent/nodes.py:429`. A bounded loop without a graph = append the `AIMessage`, run each `message.tool_calls` entry by name, append `ToolMessage(content=json, tool_call_id=...)`, re-invoke; stop after 3 tool calls and then invoke the structured-output runnable for the final answer.
- Usage: `llm_service.usage_of(message)` (`service.py:284`) reads `usage_metadata` + `response_metadata["cost"]` and returns `llm_service.Usage`; `flow_state.Usage(prompt_tokens, completion_tokens, cost: Decimal|None)` (`agent/flow_state.py:122`) is the checkpoint type — one small adapter converts, summing every call of one decision/beat.
- Read-only tool bodies to reuse: `recall` (`agent/tools.py:968`) and `lookup_rule` (`agent/tools.py:991`), both `@tool` + `@_serialized` with a `ToolRuntime[DmContext]` injected by `ToolNode`. Outside a graph there is no `ToolRuntime`, and v2 wants `recall_history`, not `recall`. Therefore write two fresh, plain async functions in the new module calling `srd_service.search_rules(db, query=, limit=)` and `playthrough_service.recall_history(db, user_id=, run_id=, query=, limit=3)` (`app/modules/playthrough/service.py:4120`), exposed to the model with `langchain_core.tools.tool` over a closure that captures `ctx`. Old `tools.py` stays untouched.
- Reference validation: `validate_refs(situation, op) -> str|None` (`agent/operations.py:64`) checks `actor_id/target_id/from_id/to_id/object_id/item_id/exit_id/choice/attack` against the situation and returns `"stale_reference"`. It takes an `Operation`; a proposed `OperationSpec` is wrapped as `Operation(operation_id="proposed", kind=..., payload=...)`.
- Evidence views: `Situation`/`SituationPublic` at `app/modules/playthrough/situation.py:113,138`; `Situation.public()` already strips `secrets`, `npc_intent` and every `FixtureView.checks` — narration takes only `SituationPublic`, which satisfies AC3 by construction.
- Prompts: `load_prompt("game/<kind>/<name>", version=)` (`app/core/prompts/service.py:100`), layout `modules/<capability>/prompts/<version>/<kind>/<name>.md`, segments lowercase-kebab, highest `v<n>` wins. Existing: `game/system/dm`, `game/system/smoke` (`app/modules/game/service.py:40`). New files go under `app/modules/game/prompts/v1/decision/` and `.../v1/narration/` — additive, old prompt untouched. No tone/personality variable exists anywhere in the prompt path today.
- Test fakes: `GenericFakeChatModel` (used in `backend/tests/game/test_service.py:11,97`, `tests/character/conftest.py:132`) needs a subclass overriding `bind_tools` (it raises `NotImplementedError`); it has no `with_structured_output` that works offline. Minimal new fake: a `BaseChatModel`-shaped stub whose `bind_tools`/`with_structured_output` return `self` and whose `ainvoke` pops the next scripted item (`AIMessage` with `tool_calls`, a parsed object, or an exception) — mirrors `_ScriptedCallModel` in `tests/game/test_narrate_seam.py`.

## Work items

- WI1 `agent/decisions.py` (+ prompt files): kinds, per-kind Pydantic output schemas, registry, `decide()` with validation, bounded retry and the 3-call tool loop, plus the two read-only tool closures.
- WI2 `agent/narration.py` (+ prompt file): `BeatKind`, `BeatRequest`, `narrate()` from `SituationPublic` and the evidence allowlist, no tools; plus `NarrativeCursor` draft handling and the documented `record_beat` contract (draft survives in state until the operation reports `ok`, then `event_id` set and `draft` cleared).
- WI3 `agent/model_call.py`: `build_model()` + `ainvoke_traced(runnable, messages, label) -> (message, flow_state.Usage)` — the shared build/usage helper both WIs import. Do WI3 first or stub its two signatures; WI1 and WI2 then run in parallel.

## Interfaces

```python
# model_call.py (WI3)
def build_model() -> BaseChatModel: ...                      # llm_service.chat_model()
def to_usage(messages: Sequence[BaseMessage]) -> Usage: ...  # flow_state.Usage, summed
async def ainvoke(runnable, messages, *, label: str) -> AIMessage: ...

# decisions.py (WI1)
class DecisionKind(StrEnum):
    READ_MOVE = "read_move"; INTERPRET_EVIDENCE = "interpret_evidence"
    JUDGE_REFERENCE = "judge_reference"; ASSESS_MOVE = "assess_move"
    MONSTER_ACTION = "monster_action"; WORLD_REACTION = "world_reaction"

@dataclass(frozen=True)
class DecisionRequest: decision_id: str; kind: DecisionKind; evidence_ids: tuple[str, ...]; payload: Mapping[str, Any]

@dataclass(frozen=True)
class DecisionResult: decision_id: str; kind: DecisionKind; value: Any; usage: Usage

@dataclass(frozen=True)
class ReadMoveDecision: intent: str; refs: Mapping[str, str]; proposed: tuple[OperationSpec, ...] | None
@dataclass(frozen=True)
class EvidenceReading: summary: str; supports: tuple[str, ...]
@dataclass(frozen=True)
class ReferenceJudgement: chosen_id: str | None; ask_choice: tuple[str, ...]
@dataclass(frozen=True)
class MoveAssessment: applies: bool; dc: int | None; dc_source: Literal["authored", "rules"] | None; consequence_ids: tuple[str, ...]
@dataclass(frozen=True)
class MonsterAction: actor_id: str; attack: str; target_id: str
@dataclass(frozen=True)
class WorldReaction: reactions: tuple[ReactionSpec, ...]

@dataclass(frozen=True)
class Strategy:
    prompt_key: str; output_schema: type[BaseModel]
    allowed_operations: frozenset[OperationKind]; binds_tools: bool
    evidence: Callable[[Situation, GameFlowState], Any]
    build: Callable[[Any, Situation], Any]   # pydantic output -> value dataclass

DECISION_HANDLERS: dict[DecisionKind, Strategy]

@dataclass(frozen=True)
class DecisionContext: db: AsyncSession; user_id: str; run_id: str; hero_id: str; situation: Situation; model: BaseChatModel

MAX_TOOL_CALLS = 3
RETRY_BUDGET = 2
class DecisionInvalid(Exception): ...
async def decide(ctx: DecisionContext, request: DecisionRequest, state: GameFlowState) -> DecisionResult: ...

# narration.py (WI2)
BeatKind = Literal["opening", "attempt", "outcome", "answer", "arrival", "refusal", "closing"]

@dataclass(frozen=True)
class BeatRequest: beat_id: str; kind: BeatKind; allowed_evidence_ids: tuple[str, ...]; payload: Mapping[str, Any]
@dataclass(frozen=True)
class BeatDraft: beat_id: str; text: str; usage: Usage

async def narrate(ctx: DecisionContext, request: BeatRequest, state: GameFlowState) -> BeatDraft: ...
def draft_state(draft: BeatDraft) -> StateDelta: ...       # {"narrative": NarrativeCursor(beat_id, draft.text, None)}
def recorded_state(beat_id: str, event_id: str) -> StateDelta: ...
```

Prompt files: `prompts/v1/decision/read-move.md`, `interpret-evidence.md`, `judge-reference.md`, `assess-move.md`, `monster-action.md`, `world-reaction.md`; `prompts/v1/narration/beat.md`.

Validation in `decide`: every `OperationSpec.kind` must be in the strategy's `allowed_operations` (itself a subset of `OperationKind`), every named id must pass `validate_refs`; a failure re-prompts with the reason, same `decision_id`, at most `RETRY_BUDGET` times, then raises `DecisionInvalid` (AC1). The tool loop counts tool calls, not turns, and stops at 3 (AC2).

Trade-off: per-kind Pydantic schemas plus dataclass values duplicate each shape once; the alternative (Pydantic everywhere in state) violates the checkpoint rule. Failure behaviour: `DecisionInvalid`/`LlmError` escape to the caller — sprint 07's `advance` maps them to `execution_error`. Blast radius: new files only; graph, old prompts and `tools.py` untouched.

## Open questions

- Should narration carry a selectable tone or DM personality? Nothing in the code offers one today, so this sprint ships a single narration voice unless the product wants otherwise.
