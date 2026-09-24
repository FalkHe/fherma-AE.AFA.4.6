# Documentation

`general/` describes the whole system. `modules/` describes one domain or
subsystem each. `roadmap/` is history — how we got here, kept for the audit
trail, not a description of the current state.

## General

| Doc | Contents |
|---|---|
| [general/app-vision.md](general/app-vision.md) | What the app is, who it is for, its core principles and what a player experiences |
| [general/architecture.md](general/architecture.md) | Guiding principle, layer boundaries, system components, the modular layout, the wire convention, request lifecycle |
| [general/model.md](general/model.md) | The data model: entities, their hierarchy and relations, the decisions behind the shape, static content files, lifecycle |
| [general/glossary.md](general/glossary.md) | The vocabulary: game terms, content terms, run terms, agent terms |
| [general/backend-stack.md](general/backend-stack.md) | Python stack, conventions and tooling |
| [general/frontend-stack.md](general/frontend-stack.md) | TypeScript stack, conventions and tooling |
| [general/requirement-map.md](general/requirement-map.md) | How the project satisfies the graded brief in `135.md` |
| [general/game-flow.md](general/game-flow.md) | The target game loop, station by station: opening, exploration, checks, combat rounds; every action with its dependencies; what the graph enforces and where the code still falls short |
| [general/game-flow.v2.md](general/game-flow.v2.md) | The implementation structure for that loop: five LangGraph nodes, typed effects and cursors, scheduling priority, registries, recovery and delivery sequence |
| [general/game-flow.v2.examples.md](general/game-flow.v2.examples.md) | Common five-node flow scenarios: conversation, checks, movement, items, fixtures, rules, recall, ambiguity, combat and terminal outcomes |

## Modules

| Doc | Contents |
|---|---|
| [modules/content.md](modules/content.md) | The adventure-content schema, its directory layout and versioning, and the authoring guide |
| [modules/playthrough.md](modules/playthrough.md) | The state a game accumulates: campaign runs, membership, adventure runs, objects and events — five tables, no surface yet |

## Roadmap

| Phase | Contents |
|---|---|
| [roadmap/phase-0/](roadmap/phase-0/) | Scaffolding: modular skeletons, authentication, blank home page |
| [roadmap/Stage-01/](roadmap/Stage-01/) | The MVP single-player release: capability inventory, eleven bottom-up phases and their milestones, scope fence, open-decision and doc-correction registers |

## Conventions for editing these docs

- State the current behaviour, not the journey to it.
- If something is not obvious, say **why** it is that way — one clause, not a
  paragraph.
- Where reality diverges from a plan, say so explicitly rather than describing
  the plan.
- Agent working advice belongs in `.claude/skills/`, not here.
