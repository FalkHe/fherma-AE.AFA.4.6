---
author: architect
owner: agent
created: 2026-09-22
updated: 2026-09-22
---
# Research: 009 Character creation

## Facts

**What ships today.** `create_character` already exists and already accepts a sheet:
`backend/app/modules/playthrough/service.py:456` (`sheet: SeedCharacter | None`), defaulting to the
pinned campaign's seed (`backend/content/campaigns/greenhollow/v1/campaign.json:6`). It writes one
`objects` row plus one carried item per inventory entry and moves the run `setup → ready`. The route
`POST /playthrough/campaign/{runId}/character` takes **no body** (`routes.py:93`), so today every run
gets Rosalind Thorn. 005-D4 already fixed that creation is "its own graph, chat and UI"; 003-D13 fixed
one character per run (`CharacterExistsError`, `service.py:485`). "Ready" is simply "a character exists"
(`service.py:409`, `schemas.py:48`).

**The sheet today.** `SeedCharacter` (`content/schemas.py:128`): name, race, characterClass, background,
appearance, abilities, maxHp, armourClass, inventory. Storage blob `CharacterState`
(`playthrough/schemas.py:160`); wire `CharacterRead` (`:149`) exposes only id/name/hp/AC. Nothing carries
level, hit die, proficiencies, skills, saves, speed or alignment. Two constraints: `SeedCharacter` is a
frozen, `extra="forbid"` **content** model (`content/schemas.py:8`), and each inventory entry must name an
existing campaign object template — `loaded.object_templates[template_id]` (`service.py:523`) raises on
anything else, so a player-picked SRD item has nowhere to come from.

**SRD.** Corpus shipped at `backend/content/srd/v1/SRD_CC_v5.1.md` (1.9 MB); ingest, search and status are
live (`srd/service.py:304,425,58`; `app srd ingest|search|status`). It holds 9 races (`:5`), 12 classes
(`:375`) each with Hit Points / Proficiencies / Equipment (e.g. Barbarian `:545,:553,:565`), **exactly one
background — Acolyte** (`:8013`), ability modifiers (`:6792`), proficiency bonus (`:6896`), skills
(`:6964`), alignment (`:7855`), equipment and packs (`:18725,:19510`). It contains **no ability-score
generation rules** — no standard array, no point buy, no 4d6-drop-lowest for characters — and no
step-by-step creation chapter. Those are ours to author. No structured (machine-readable) race/class data
exists anywhere in the repo; the chunks are prose.

**Agent infrastructure.** Reusable as-is: graph builder (`game/agent/graph.py:15`), `build_agent`/`turn`/
`resume` (`game/service.py:40`), interrupt-based `ask_player`, Postgres checkpointer
(`core/checkpointer/service.py:49`), tracing, prompts resolved per owning capability
(`core/prompts/service.py:100`; `docs/general/model.md:306` says a character-generation prompt must not
live under `game`). An interactive terminal loop already exists (`app game play`, `game/commands.py:172`).
No `lookup_rule` tool yet (008 `agent-implementation.md`, item 13).

**Frontend.** Nothing character-related: `DashboardRoute` is a heading (`home/routes/DashboardRoute.tsx:16`),
007 sprints 05–09 still open. The update pattern is a notice-only SSE plus refetch (`routes.py:189`).
`with_structured_output(PydanticModel)` exists in langchain-core 1.6.3 / langchain 1.4.2 (`backend/uv.lock`)
— verified via context7 — but is unused here, and support in `ChatOpenRouter` (langchain-openrouter 0.2.8)
is unverified.

## Options

**Part 1 — sheet model and deterministic builder**

| Option | Pro | Con |
|---|---|---|
| A: widen `SeedCharacter` + `CharacterState` | no new module; `create_character` untouched | the content module would own a player concept; authored campaigns must carry fields they never use |
| B: new `character` module — its own sheet schema, pure builder functions, and a small authored SRD options file (races/classes/backgrounds as data) | numbers stay deterministic and unit-testable; clean ownership; `create_character` already takes a sheet | the options file must be kept true to the SRD text by review |
| C: let the agent read the rules and fill the numbers | nothing to author | breaks "mechanics never come from the LLM"; unreproducible |

Recommendation: **B**, over a deliberately small option set. Trade-off: hand-authored data to maintain.
Failure behavior: an invalid sheet is refused by validation before any row is written. Blast radius: one
new module plus a body on the existing route.

**Part 2 — creation agent**

| Option | Pro | Con |
|---|---|---|
| A: own small graph in `character`, tools = the builder functions, questions via the existing interrupt | matches 005-D4; the DM graph stays untouched; the LLM only asks and proposes | a second graph to maintain |
| B: a mode on the DM graph | one graph | two prompts and two tool sets behind one entry point; every DM turn pays for it |
| C: structured output only, no graph | simplest | no dialogue; an unverified model capability |

Recommendation: **A**. Failure behavior: a model failure leaves the run without a character; nothing is
half-written, because the sheet is only committed once complete and valid. Blast radius: new module only.

**Part 3 — the player-facing surface**

| Option | Pro | Con |
|---|---|---|
| A: terminal first (`app character create`), mirroring `app game play` | the whole loop is playable with no frontend work | not the player's surface |
| B: a chat page inside the run screen, one request per message, refetch on change | matches the existing notice-plus-refetch pattern | needs 007/05 to land first |
| C: token streaming | feels fast | new transport, new failure modes, no precedent here |

Recommendation: **A first, then B**; no token streaming.

## Assumptions

New `character` module owning sheet, builder, prompt and graph · SRD level 1 only · starting equipment
limited to the campaign's existing item templates until a starter-gear set is authored · alignment stored
as free text · the seed character stays as a fallback · abandoned creation chat: nothing is kept until the sheet is confirmed, the player starts over (← D12, least effort: no session-to-run mapping, no resume entry point).

## Open questions

1. Which races and classes may a player pick — all SRD, or a short curated list?
2. How are ability scores set: standard array, point buy, rolled dice, or the agent proposing a set?
3. How much does the player type freely versus pick from offered choices?
4. The SRD ships one background only. Offer just that, let the player write their own, or let the agent invent one?
5. Starting equipment: a fixed pack per class, or a choice?
6. May a character be changed or replaced after creation but before play starts?
7. Who writes name, looks and backstory — the player, or the agent proposing and the player approving?
8. Does the current one-click "use the ready-made character" stay as a skip option?
9. Is a terminal-only first delivery acceptable, with the player-facing screen in a later sprint?
