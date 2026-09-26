---
author: fhit:architect
owner: agent
created: 2026-09-26
---
# Research — Sprint 09: remove the old flow

## Facts

The unstaged diff (branch `cleanup/sprint-09-remove-old-flow`) already does
the bulk of the work and is sound:

- Deletes `backend/app/modules/game/agent/{nodes,state,tools}.py` (old
  node factories, `DmState`/`DmContext`, the 1050-line tool registry) and
  `backend/app/modules/game/prompts/v1/system/dm.md`.
- Drops the guard from the new flow: `advance.guard_refusal`/`guard_state`
  and the guard branch in `flow_nodes.advance:159` and
  `advance.advance_action:852`; removes the dead `system_prompt` parameter
  from `graph.build_graph:29`.
- Deletes the obsolete suites (`test_actor_resolution.py`,
  `test_lookup_rule_visible_entry.py`, `test_turn_mechanics_summary.py`,
  `test_run_turn.py` old cases, `playthrough/test_ac4_tools_never_write_events.py`)
  and trims `test_commands.py`, `core/prompts/test_*.py`.
- Rewrites `backend/app/modules/game/README.md` to the five-node flow with
  `lookup_rule`/`recall_history` as read-only aids (README.md:1-45), and
  updates `docs/general/{architecture,glossary,model,requirement-map}.md`,
  `docs/README.md` (drops the `general/game-flow.md` row — the file is
  already gone) and deletes `docs/refactoring/*`.

Verified: `docker compose run --rm --no-deps app-cli ruff check .` → "All
checks passed"; importing `game.agent.graph`, `game.service`,
`game.commands`, `game.agent.advance`, `playthrough.service` and
`character.agent.graph` succeeds. No broken imports, no dead helpers left
in `game/agent`. Tests not run (out of scope here).

Remaining references to the old flow:

1. `backend/app/modules/character/agent/graph.py:2` — docstring names the
   removed game nodes `load_context`, `record_action`/`record_narration`,
   `guard`.
2. `backend/tests/game/test_commands.py:460,468` — checkpoint fixtures use
   the removed step names `record_narration`, `narrate`, `load_context` as
   `next`/`writes` values.
3. `docs/architecture.md:9-27` — still says "State: **scaffolding** … The
   game agent does not [exist]" and lists only `auth`, `users`, `health`.
4. `docs/intents/008-headless-dm-agent/agent-graph.png` — the generated
   diagram of the old graph (AC2); unreferenced by any doc or Makefile.
   The generator itself (`app game graph`, `game/commands.py:213-253`)
   draws the current graph and stays.
5. `backend/app/modules/game/prompts/v1/system/smoke.md` — the last
   `game/system/` prompt; no code references it (prompt CLI tests build
   their own under `tmp_path`).

## Work items

- **WI1 — code**: remove the stale old-flow mentions in
  `backend/app/modules/character/agent/graph.py` and decide/remove
  `game/prompts/v1/system/smoke.md`.
- **WI2 — tests**: `backend/tests/game/test_commands.py` checkpoint
  fixtures use current node names (`advance`, `narrate`, `execute`).
- **WI3 — docs (index/architecture)**: `docs/architecture.md` describes the
  real current state (game agent exists, module list, five-node flow);
  confirm `docs/README.md` has no dangling rows.
- **WI4 — artifact**: delete `docs/intents/008-headless-dm-agent/agent-graph.png`.
- **WI5 — verification**: full backend suite plus linter green (AC4), and a
  repo-wide search for the removed names returns nothing (AC1).

## Interfaces

None — WI1–WI4 touch disjoint files and can run in parallel; WI5 runs last.

## Open questions

- The prompt-injection refusal patterns are gone with the old guard step.
  `docs/general/requirement-map.md:30` now satisfies "security guard" with
  ownership/authentication boundaries only. Confirm that is the intended
  product behaviour for the graded criterion.
