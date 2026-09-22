# Playthrough Service Refactoring Plan

This document outlines the refactoring strategy for `backend/app/modules/playthrough/service.py` to break down its large footprint into cohesive, focused domain modules while preserving architectural conventions and test compatibility.

---

## 1. Current State Analysis

`backend/app/modules/playthrough/service.py` currently combines multiple distinct responsibilities:

1. **Campaign & Character Lifecycle**: Run creation, membership verification, initial world object seeding, character generation, renaming, archiving, and activation (`start_campaign_run`, `create_character`, `archive_campaign_run`, `_build_run_objects`, etc.).
2. **Adventure & Navigation**: Adventure progression, scene transitions, and campaign completion (`enter_adventure`, `use_exit`).
3. **Core Mechanics & Dice Resolution**: Player prompts, roll derivation, passive checks, initiative, and DC resolution (`request_player_roll`, `resolve_roll_request`, `roll`, `roll_initiative`, `passive_check`, `resolve_check`, `resolve_save`).
4. **World & Inventory Actions**: Single-action enforcement, fixture interaction, and inventory transfers (`interact`, `take`, `drop`, `give`, `use_item`).
5. **Combat Resolution**: Attack resolution (AC vs. roll, critical hits) and damage application with character down / death tracking (`attack`, `damage`, `_consume_hit`).
6. **Transcript, Event Logging & Memory (RAG)**: Central event sink, turn cost aggregation, live SSE signal helpers, recaps, and vector similarity recall (`append_event`, `list_events`, `get_awaiting`, `run_cost`, `latest_event_id`, `recap`, `recall`).

---

## 2. Proposed Domain Grouping

Partition the file's contents into focused sub-modules under `backend/app/modules/playthrough/`:

```
backend/app/modules/playthrough/
├── service.py               # Public API / Facade re-exporting all functions
├── runs.py                  # Campaign runs, memberships, characters, lifecycle
├── navigation.py            # Adventure entry, scene exits, completions
├── mechanics/
│   ├── actions.py           # interact, take, drop, give, use_item, action gates
│   ├── combat.py            # attack, damage, hit tracking
│   └── rolls.py             # roll, resolve_check, resolve_save, passive_check, initiative
├── events.py                # append_event, list_events, latest_event_id, run_cost, get_awaiting
└── memory.py                # recap, recall (RAG vector searches)
```

### Sub-module Responsibilities

#### Run & Character Lifecycle (`runs.py`)
- **Functions**: `start_campaign_run`, `list_campaign_runs`, `get_campaign_run`, `create_character`, `rename_campaign_run`, `archive_campaign_run`, `activate_campaign_run`.
- **Internal Helpers**: `_build_object`, `_build_run_objects`, `_require_member`, `_get_run`, `_require_writable`.
- **Responsibility**: Database entity persistence and run-level state progression.

#### Navigation & Scene Flow (`navigation.py`)
- **Functions**: `enter_adventure`, `use_exit`.
- **Internal Helpers**: `_refuse_exit`, `_resolve_actor_and_run`, `_require_ready_or_active_run`.
- **Responsibility**: Positioning actors, transitioning across scenes, and marking adventure/campaign completion.

#### Game Mechanics (`mechanics/`)
- **Rolls & Checks (`rolls.py`)**: `request_player_roll`, `resolve_roll_request`, `roll`, `roll_initiative`, `passive_check`, `resolve_check`, `resolve_save`, `ask_player`, `_consume_roll`, `_refuse_roll`, `_resolve_roll_outcome`.
- **Actions & Inventory (`actions.py`)**: `interact`, `take`, `drop`, `give`, `use_item`, `_item_reachable`, `_already_acted`, `_refuse_move`, `_refuse_interact`.
- **Combat (`combat.py`)**: `attack`, `damage`, `_consume_hit`, `_refuse_attack`, `_refuse_damage`, `_hit_already_damaged`.
- **Responsibility**: Rules execution, transcript turn-consumption rules (1 action per turn, single-use rolls), and refusal event commits.

#### Transcript & Event Log (`events.py`)
- **Functions**: `append_event`, `list_events`, `get_awaiting`, `run_cost`, `latest_event_id`.
- **Responsibility**: Immutable event persistence, payload validation, token/cost tracking, and query cursors.

#### Memory & RAG (`memory.py`)
- **Functions**: `recap`, `recall`.
- **Responsibility**: LLM embeddings and cosine-distance search over narration events.

---

## 3. Architectural Options & Trade-off Evaluation

### Option A: Facade Pattern via `service.py` (Recommended)
Keep `backend/app/modules/playthrough/service.py` as a lightweight dispatch module that imports and re-exports all public service functions from internal modules (`runs.py`, `events.py`, `mechanics/`, etc.).

- **Pros**:
  - **Zero Breaking Changes**: Preserves the project guideline (`from app.modules.playthrough import service` and `service.foo(...)`).
  - **Test Compatibility**: Preserves monkeypatching targets in the test suite (`monkeypatch.setattr(service, "append_event", ...)` continues to work uninterrupted).
  - **Incremental Migration**: Each domain slice can be extracted independently without modifying route or command callers.
- **Cons**:
  - Requires maintaining explicit re-exports or `__all__` in `service.py`.

### Option B: Turn `service` into a Package Directory (`service/__init__.py`)
Replace `backend/app/modules/playthrough/service.py` with `backend/app/modules/playthrough/service/` containing `__init__.py` and sub-modules.

- **Pros**:
  - Groups all service sub-modules cleanly under a single directory.
- **Cons**:
  - Git history for `service.py` is fragmented across new files.
  - Risk of import path ambiguities during refactoring.

---

## 4. Step-by-Step Separation Plan

1. **Phase 1: Extract Leaf Modules (Transcript & Memory)**
   - Move `recap` and `recall` to `backend/app/modules/playthrough/memory.py`.
   - Move `append_event`, `list_events`, `latest_event_id`, `run_cost`, and `get_awaiting` to `backend/app/modules/playthrough/events.py`.
   - Re-export them in `service.py` and run tests.

2. **Phase 2: Extract Rules & Mechanics Engine**
   - Move roll resolution, action handling, and combat resolution into `backend/app/modules/playthrough/mechanics/`.
   - Re-export in `service.py` and verify all acceptance tests.

3. **Phase 3: Extract Run Lifecycle & Navigation**
   - Move run creation and character setup into `backend/app/modules/playthrough/runs.py` and navigation into `backend/app/modules/playthrough/navigation.py`.
   - Retain `service.py` as the top-level facade module.
