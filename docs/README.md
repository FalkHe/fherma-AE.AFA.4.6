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

## Modules

*None yet — the first module doc lands with the first subsystem.*

## Roadmap

| Phase | Contents |
|---|---|
| [roadmap/phase-0/](roadmap/phase-0/) | Scaffolding: modular skeletons, authentication, blank home page |
| [roadmap/Stage-01/](roadmap/Stage-01/) | The MVP single-player release: capability inventory, twelve phases and their milestones, scope fence, open-decision and doc-correction registers |

## Conventions for editing these docs

- State the current behaviour, not the journey to it.
- If something is not obvious, say **why** it is that way — one clause, not a
  paragraph.
- Where reality diverges from a plan, say so explicitly rather than describing
  the plan.
- Agent working advice belongs in `.claude/skills/`, not here.
