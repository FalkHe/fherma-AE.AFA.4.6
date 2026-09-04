# Documentation

`general/` describes the whole system. `modules/` describes one domain or
subsystem each. `roadmap/` is history — how we got here, kept for the audit
trail, not a description of the current state.

## General

| Doc | Contents |
|---|---|
| [general/project-vision.md](general/project-vision.md) | What this is, why the catalogue is curated, course context and graded requirements |
| [general/architecture.md](general/architecture.md) | Repo layout, API conventions, jobs, realtime, agent boundaries, deployment |
| [general/decisions.md](general/decisions.md) | Non-obvious choices with their reasons · open owner decisions · what we deliberately did not build |
| [general/security.md](general/security.md) | Auth, authorization surface, validation caps, prompt-injection fencing, known gaps |
| [general/observability.md](general/observability.md) | Logging and the (narrow) Langfuse integration |
| [general/backend-stack.md](general/backend-stack.md) | Python stack, justifications, exclusions |
| [general/frontend-stack.md](general/frontend-stack.md) | React stack, justifications, conventions |

## Modules

| Doc | Contents |
|---|---|
| [modules/ingestion.md](modules/ingestion.md) | Name → documents, draft spec, image, embeddings. Stages, prompts, error policy, CLI, configuration |
| [modules/catalogue.md](modules/catalogue.md) | Tables, spec fields, transition matrix, admin and customer APIs, both UIs |
| [modules/model-naming.md](modules/model-naming.md) | Motorcycle naming as a domain, then how identity is actually modelled and rendered |
| [modules/retrieval-advisor.md](modules/retrieval-advisor.md) | Hybrid retrieval, query translation, the eight tools, the advisor loop |
| [modules/chat-consultation.md](modules/chat-consultation.md) | Chat tables, turn lifecycle, wire shapes, SSE, chat UI |
| [modules/used-prices.md](modules/used-prices.md) | **Storage and UI only** — what exists, what does not, and why the sources constrain it |
| [modules/demo-data.md](modules/demo-data.md) | Seed, snapshot, suggestion import, scripted consultation |

## Roadmap (history)

[roadmap/roadmap.md](roadmap/roadmap.md) plus one directory per phase
(`summary.md` = what that phase delivered, decided and deferred — start here;
`shared-knowledge.md` = the binding contract for that phase and its `Landed
decisions`; step files, `open-questions.md`, `ui-spec.md`). Phase 6's
`model-naming-data-model.md` and `model-naming-display-spec.md` hold the
identity rationale.

**Phases 0–5 are complete. Phase 6 is not**: its identity track landed, its
used-price track stopped after storage, and its documentation and acceptance
steps did not run. Where a phase document and the code disagree, the code wins
and `general/`+`modules/` should already say so.

## Conventions for editing these docs

- State the current behaviour, not the journey to it.
- If something is not obvious, say **why** it is that way — one clause, not a
  paragraph.
- Where reality diverges from a plan, say so explicitly rather than describing
  the plan.
- Agent working advice belongs in `.claude/skills/`, not here.
