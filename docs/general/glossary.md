# Glossary

The vocabulary this project uses, in one place. Terms are used exactly as
defined here — in code, in content and in the UI.

## Game terms (D&D 5e SRD)

- **d20** — 20-sided die. Every uncertain outcome is `d20 + bonus` against a
  target number.
- **DC (Difficulty Class)** — the target number for a check. Easy 10,
  medium 15, hard 20.
- **AC (Armour Class)** — the target number an attacker must reach to hit you.
- **HP (Hit Points)** — health. 0 means down.
- **Passive check** — `10 + bonus` against a DC, with no roll. Used for
  noticing hidden things without leaking that there was something to notice.
- **Initiative** — `d20 + Dexterity bonus`, determines turn order in combat.
- **SRD** — System Reference Document; the freely licensed subset of the D&D
  5e rules (SRD 5.1, CC-BY-4.0). The only corpus behind RAG here.

## Content terms

Authored material, static JSON in git. See [model.md](model.md).

- **Campaign** — a series of adventures. The largest unit of content.
- **Adventure** — one story within a campaign, three or more scenes.
- **Scene** — one place or situation, written as facts, intentions and
  consequences rather than as a script.
- **Definition** — a campaign-scoped NPC or monster stat block that scenes
  reference by id.
- **Content version** — the revision of a campaign a playthrough is pinned to.
  Content is extended by publishing a new version, never by editing in place.

## Run terms

Mutable state in Postgres. See [model.md](model.md).

- **Playthrough** — one player's run of one campaign, spanning all of its
  adventures with the same character. Deliberately not called a "session",
  which is reserved for browser/HTTP sessions.
- **Adventure run** — the progress of one adventure inside a playthrough.
- **Object** — any interactable thing in a run: creature, item or fixture. The
  player character is a creature.
- **Encounter** — one fight: participant order, round counter, turn pointer.
- **Event** — *what happened*. The append-only stream of narration, player
  input, rolls, tool calls, errors and cost.
- **Journal entry** — *what is true*. Agent-written, embedded durable canon,
  retrieved by similarity. Facts, not a transcript.

## Agent terms

- **Tool** — deterministic code the agent calls: dice, state mutation,
  lookups. The agent never fakes a roll or edits state directly.
- **Checkpointer** — LangGraph's store for the conversation and graph
  plumbing. Rebuildable; not a source of truth.
- **Guard node** — the check that runs before the agent, rejecting prompt
  injection and out-of-band state changes ("my HP is 100").
- **RAG** — retrieval-augmented generation. Here it means SRD lookups only;
  structured content is read from JSON, never retrieved.
- **Agentic RAG** — the agent decides whether to look a rule up, and may
  re-query.
- **Human-in-the-loop** — the agent interrupts and waits for the player
  whenever a decision is theirs (`ask_player`).
- **Developer drawer** — the part of the UI holding model, temperature,
  system prompt and DM personality, kept out of the player experience.

## Planning terms

- **Stage** — a release. Stage-01 is the MVP.
- **Phase** — one unit of a stage. A phase ships exactly one **milestone**, and
  its completion *is* that milestone.
- **Milestone** — a finished, self-contained capability, falsifiable by
  evidence a reviewer can produce. Never half a capability parked for later.
- **Step** — one unit of a phase, with its own step spec and its own phase
  directory. Steps are defined when the phase is planned, not before.
- **Roadmap** — the stage's phase plan. It says what and in what order, never
  how: no tables, routes, payload shapes or file layout.
