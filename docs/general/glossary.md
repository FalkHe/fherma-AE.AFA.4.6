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
  The game uses a simplified house rule: one hero-side roll and one hostile-side
  roll establish which side acts first for the fight; the hero side wins a tie.
  The active order lives in the LangGraph checkpoint, not the run model.
- **SRD** — System Reference Document; the freely licensed subset of the D&D
  5e rules (SRD 5.1, CC-BY-4.0). The only corpus behind RAG here.

## Content terms

Authored material, static JSON in git. See [model.md](model.md).

**The word *content* covers two different things and is never used bare where
the two could be confused.** *Story* / *Prose* is the narrative text; a
*Campaign-Definition* / *Adventure-Definition* is the authored structure that
carries it and that Story references by id. "The content module", "the content
tree" and "content version" remain the names of the authoring subsystem as a
whole, where no ambiguity is possible.

- **Campaign** — a series of adventures. The largest authored unit.
- **Campaign-Definition** — the authored JSON structure of a campaign:
  `campaign.json` — its metadata, its ordered adventure list, its object
  templates and its seed player character. Structure, never narrative.
- **Adventure** — one story within a campaign, three or more scenes.
- **Adventure-Definition** — the authored JSON structure of one adventure:
  `adventures/<id>.json` — its entry scene and its scenes.
- **Scene** — one place or situation, written as facts, intentions and
  consequences rather than as a script.
- **Story** / **Prose** — the narrative text inside a scene and its adventure:
  `truth`, `npc_intent`, `consequences`, descriptions, intros. What the DM reads
  and retells; never a structure a rule resolves against.
- **Object template** (`ObjectTemplate`) — the campaign-scoped blueprint of one
  creature, item or fixture, which a scene references by id; each placement of
  it becomes one `objects` row when a run starts. It is discriminated by
  `kind` — `CreatureTemplate`, `ItemTemplate`, `FixtureTemplate` — so each kind
  carries exactly the fields the mechanics need to resolve interactions against
  it. Template and instance are different things with different lifetimes:
  *creature* is the instance's word, *object template* is the blueprint's.
- **Content version** — pinned-revision jargon: the revision of a campaign a
  campaign run is pinned to. A campaign is extended by publishing a new version,
  never by editing one in place.

## Run terms

Mutable state in Postgres. See [model.md](model.md).

- **Campaign run** (`campaign_runs`) — one player's run of one campaign,
  spanning all of its adventures with the same character; the row everything
  else in a run hangs off. Not a "session" (reserved for browser/HTTP sessions)
  and not a "playthrough", which names the activity and the module, never the
  entity.
- **Adventure run** (`adventure_runs`) — one adventure being played inside a
  campaign run: which adventure was entered, when, and whether it is done.
- **Object** (`objects`) — any interactable thing in a run: creature, item or
  fixture. The player character is a creature.
- **Seed player character** — the authored fixture a campaign run instantiates
  the player's creature from until the generation agent lands.
- **Encounter** — one fight: participant order, round counter, turn pointer.
  Deferred to the DM-turn phase; this phase builds no combat state, so no run
  entity carries it.
- **Event** — *what happened*. The append-only stream of narration, player
  input, rolls, tool calls, errors and cost; its narration events are the DM's
  long-term memory.

## Agent terms

- **Tool** — deterministic code the agent calls: dice, state mutation,
  lookups. The agent never fakes a roll or edits state directly.
- **Checkpointer** — LangGraph's store for active turn and combat cursors,
  requests, results and narration progress. Rebuildable; not a source of truth
  for durable world facts.
- **RAG** — retrieval-augmented generation. Here it means SRD lookups only;
  structured content is read from JSON, never retrieved.
- **Agentic RAG** — the agent decides whether to look a rule up, and may
  re-query.
- **Human-in-the-loop** — the graph interrupts and waits for the player at
  `await_player` whenever a decision is theirs.
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
