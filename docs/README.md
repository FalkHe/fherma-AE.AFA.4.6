# Documentation

`general/` describes the whole system. `modules/` describes one domain or
subsystem each. `roadmap/` is history — how we got here, kept for the audit
trail, not a description of the current state.

## General

| Doc | Contents |
|---|---|
| [general/project-vision.md](general/project-vision.md) | What this is, the content hierarchy, the vocabulary, course context and graded requirements |
| [general/architecture.md](general/architecture.md) | Layer boundaries, the modular layout, the wire convention, request lifecycle |
| [general/backend-stack.md](general/backend-stack.md) | Python stack, conventions and tooling |
| [general/frontend-stack.md](general/frontend-stack.md) | TypeScript stack, conventions and tooling |

## Modules

*None yet — the first module doc lands with the first subsystem.*

## Roadmap

| Phase | Contents |
|---|---|
| [roadmap/phase-0/](roadmap/phase-0/) | Scaffolding: modular skeletons, authentication, blank home page |

## Conventions for editing these docs

- State the current behaviour, not the journey to it.
- If something is not obvious, say **why** it is that way — one clause, not a
  paragraph.
- Where reality diverges from a plan, say so explicitly rather than describing
  the plan.
- Agent working advice belongs in `.claude/skills/`, not here.
