---
author: architect
owner: agent
created: 2026-09-22
---
# Research: sprint 009-03

## Facts

- DM graph: `build_graph(model, *, system_prompt, checkpointer)` (`backend/app/modules/game/agent/graph.py:15`); nodes are factories (`nodes.py:281` `make_narrate` binds `TOOLS` at `:282`, `nodes.py:301` `make_tools` → `ToolNode(TOOLS, handle_tool_errors=…)`); `DmContext` dataclass carries db/user/run and never reaches the model's schema (`state.py:36`).
- `game/service.py:40` `build_agent(model=None, checkpointer=None, prompt_version=None)` defaults to `InMemorySaver()` (`:49`); `turn()` (`:66`) invokes with one `HumanMessage` and a `thread_id`; `resume()` (`:85`) exists only for `interrupt()` tools (`agent/tools.py:63,84`).
- `app game play` (`game/commands.py:172`) reads lines with `asyncio.to_thread(input, "> ")` (`:134`), quits on `quit/exit/:q/empty` (`:138`), opens **one session per turn** via `get_sessionmaker()` (`:26`), and wraps the loop in `checkpointer_service.checkpointer()` (`:79`, Postgres saver, `core/checkpointer/service.py:49`).
- character module: `service.build_sheet(request)` (`character/service.py:80`) → `builder.build_sheet` (`builder.py:213`) validates point buy and derives HP/AC/saves/attacks. `builder.suggested_scores(class)` (`:96`) returns 15/14/13/12/10/8 over a per-class priority — exactly 27 points. Empty `equipment_picks` default to option 0 (`builder.py:199`), empty `free_ability_bonuses` are auto-assigned (`builder.py:111`). `CharacterCreateRequest` (`schemas.py:204`) requires `alignment`.
- `playthrough.service.create_character(db, *, user_id, run_id, sheet)` (`playthrough/service.py:457`): `sheet=None` writes the campaign's seed hero, a `CharacterSheet` writes the built one; refuses a second character; commits once.
- Seed hero of the only campaign: **Rosalind Thorn** (`backend/content/campaigns/greenhollow/v1/campaign.json:7`), reachable as `content_service.load_campaign(run.campaign_id, run.content_version).campaign.seed_character` (`content/service.py:76`, `content/schemas.py:128,149`) after `playthrough.service.get_campaign_run` (`:351`).
- Prompts resolve per owning capability, `<capability>/prompts/v<n>/<kind>/<id>.md` (`core/prompts/service.py:100`); a creation prompt must **not** live under `game/` (`docs/general/model.md:306`).
- Tests: `_ToolAwareFakeModel(GenericFakeChatModel)` with a no-op `bind_tools` (`tests/game/test_service.py:65`), scripted via `_scripted_model([AIMessage(...), …])` (`:117`), a `_FakeDb` (`:86`); CLI scenarios monkeypatch `service.chat_model` and `commands.get_sessionmaker`, then `runner.invoke(cli, [...], input="…\n")` (`:834`).
- langgraph 1.2.11 (`backend/uv.lock:526`), langchain-core 1.6.3 — source read locally at `/opt/venv/lib/python3.12/site-packages/langgraph/prebuilt/tool_node.py`: `ToolRuntime` exposes `.state`, `.context`, `.tool_call_id`, and `ToolNode` accepts a tool returning `Command(update={"messages": [ToolMessage(...)], …})`. (langgraph 1.2.11 — source: local.)

## Decisions (technical)

1. **Plain turn-taking, no interrupt.** In a terminal the Keeper's question *is* its reply and the next line is the answer; `ask_player`/`resume` exist only because the DM must hand structured questions to an API. So: no interrupt tool, no `resume()`, no question events.
2. **Two-node graph** `talk ⇄ tools` (`talk` → conditional → `tools` → `talk`; else END). No `load_context`, `record_action`, `record_narration` or `guard`: creation writes no events, and until the save tool runs there is nothing to protect.
3. **In-memory checkpointer only** (← D12): `build_creation_agent` defaults to `InMemorySaver()` and the command does *not* open the Postgres saver. AC5 then needs no code — no row is written before `save_character`, and the thread dies with the process.
4. **The draft lives in graph state**, a `CharacterCreateRequest`-shaped `dict`; writing tools return `Command(update={…})`, reading tools use `runtime.state`. The model may pass only names and free text; every number comes from `build_sheet`/`suggested_scores` (AC3).
5. **One write site**: `save_character(confirmed, ready_made=False)` merges the caller's proposed `take_ready_made` into the save tool, so the "only write" invariant and the confirmation rule exist once.
6. **Greeting is deterministic** (`render_greeting`), not model-generated, so AC1 cannot depend on the model repeating a name correctly.
7. ASSUMPTION (veto-able): alignment is not asked this sprint (out of scope) yet the sheet needs one — the draft defaults to `Neutral`; sprint 04 replaces it with the D13 question.
8. ASSUMPTION: tool refusals return in-voice text instead of raising (D16); `handle_tool_errors` returns the in-voice fallback for anything unexpected.

## Work items

- **WI1 agent** — `character/agent/{state,tools,graph}.py`, `character/prompts/v1/system/creator.md`, and `character/service.py` gaining `build_creation_agent`, `turn`, `render_sheet`, `render_seed`, `render_greeting`.
- **WI2 terminal + tests** — `app character create` in `character/commands.py`, `backend/tests/character/test_creation_agent.py` (six scenarios), README update.

Splitting is worth it: WI2 is written against the fixed interface below and its six tests are the bulk of the sprint.

## Interfaces

```python
# character/agent/state.py
@dataclass
class CreationContext:                     # never in a tool's model-facing schema
    db: AsyncSession; user_id: str; run_id: str
    ready_made: SeedCharacter | None = None

class CreationState(MessagesState):
    draft: NotRequired[dict[str, Any]]     # keys: name, race, character_class,
                                           # abilities, appearance, backstory
    saved: NotRequired[bool]

# character/agent/tools.py — TOOLS, model-facing signatures only
list_options() -> str                      # 9 races + 12 classes, one-line hint each
set_race_and_class(race: RaceName, character_class: ClassName) -> Command
set_identity(name: str, appearance: str = "", backstory: str = "") -> Command
suggest_scores() -> Command                # class read from the draft, not from the model
show_sheet() -> str                        # build_sheet(draft) -> render_sheet; in-voice list of gaps
save_character(confirmed: bool, ready_made: bool = False) -> str   # the ONLY write

# character/service.py
def build_creation_agent(*, model=None, checkpointer=None, prompt_version=None) -> CompiledStateGraph
async def turn(agent, *, thread_id: str, context: CreationContext, player_text: str) -> CreationTurn
@dataclass(frozen=True)
class CreationTurn: reply: str; saved: bool
def render_sheet(sheet: CharacterSheet) -> str      # deterministic review text (D14 §1.12 fields)
def render_seed(seed: SeedCharacter) -> str
def render_greeting(campaign_title: str, seed: SeedCharacter) -> str
```

Prompt id `character/system/creator`. Draft → request: `alignment="Neutral"`, `skills=[]`, `equipment_picks=[]`, `free_ability_bonuses=[]`. `save_character` without `confirmed=True` returns the in-voice refusal and writes nothing; with it, `build_sheet` → `create_character(sheet=…)`, or `create_character(sheet=None)` when `ready_made`, then `Command(update={"saved": True})`. CLI: `app character create --run <id> --user <id>`, one session at startup (run → campaign → seed) and one per turn, `quit` breaks, on `saved` print the finality line and exit 0.

Tests (all `runner.invoke` + scripted model): AC1 greeting names Rosalind, "take Rosalind" → `create_character(sheet=None)`; AC2 `set_race_and_class` only after the player's yes, missing race → suggestions; AC3 printed HP/AC equal `service.build_sheet(same request)`; AC4 `render_sheet` printed before the save call, `confirmed=False` writes nothing; AC5 `quit` → no `create_character` call; AC6 the prompt file contains "Tavern Keeper" while an `ast` walk over `character/**/*.py` finds no identifier containing "tavern"/"keeper".

## Open questions

None product-visible.
