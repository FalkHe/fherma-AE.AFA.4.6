---
author: fhit:architect
owner: agent
created: 2026-09-21
---
# Research: sprint 03 — the docs describe the memory the product has

Prose only; verification is reading the five files and one grep.

## Facts

Per criterion — location, and what it claims today (the argument to invert):

- **AC1** `docs/general/model.md:186` `### Situational facts have no flag store` — line 188 calls "the alarm was
  raised" a *journal entry*; 193 ends on "a mis-retrieved journal entry can un-raise an alarm".
  `model.md:195` `### Events and journal are two things` — 197 "an event is what happened, a journal entry is what is
  true"; 202-205 "nothing is pruned and nothing is retrieved by meaning"; 207-216 the DM writes canon through
  `add_journal_entry`, top-k plus recent-N, classified; 218 "not a transcript"; 220-224 *Rejected alternative — one
  table*, because embedding every narration line collapses quality and cost and a nullable vector on the hottest
  table fuses two lifecycles. That is now the ruling, inverted in place (← D1, D2): only narration is encoded, never
  player text; the nullable vector is the design; "never pruned versus curated" never held — Stage 01 prunes and
  curates nothing.
  `model.md:226` `### One embedding model, two tables` — 228-231 journal and SRD share model, pinned dimension and
  cost line; 233-240 not one table, because a journal entry cascades with the run, points at an object and is
  classified. The conclusion survives; the two stores are now `events` and `srd_rules`, and the per-row model name
  already ships. Heading may be renamed — nothing links these anchors.
- **AC2** `model.md:339` `## Known gaps`, gap 1 at `:343` — "a mis-retrieved journal entry can contradict
  established canon". Same gap, new carrier: a narration line once true, still returned as a hit.
- **AC3** `docs/general/glossary.md:76-77` **Journal entry** — "what is true, agent-written, embedded durable canon";
  delete. `:74-75` **Event** — "what happened, append-only stream"; gains the long-term-memory clause.
- **AC4** `docs/general/architecture.md:74` — table row `| add_journal_entry() / search_journal() | Long-term
  memory |`, inside the game-agent tool table (`:66-76`).
- **AC5** `docs/general/requirement-map.md:29` — `| Medium 2 … | LangGraph checkpointer (short), journal entries
  (long) |`.
- **AC6** `docs/intents/005-game-state-services/decisions/mechanics.md:83-84` — reads line lists `record_fact(text)`,
  closing "plus the one journal write"; `:62` "scene secrets … remembered by phase 6's journal". The `D`-list lives in
  `../decisions.md`, untouched; the attachment is `owner: human, stage: approved`, so bump `updated:` and change
  nothing but those two lines.

**AC7 grep** (all 9 hits **must change** — none frames the journal as rejected or Stage-02 today):

| Hit | Why |
|---|---|
| `model.md:34` | `JournalEntry` node in the entity diagram — **not named by AC1-AC6**, removed under AC7 |
| `model.md:42`, `:45` | ownership bullets list "the journal" among the run's rows — same sweep |
| `model.md:188`, `:193`, `:195`, `:197`, `:207`, `:218`, `:221` | AC1; afterwards the word survives **only** in the inverted rejected-alternative paragraph and any Stage-02 sentence (← D1) |
| `model.md:343` · `glossary.md:76` · `architecture.md:74` · `requirement-map.md:29` · `mechanics.md:62`, `:84` | AC2 · AC3 · AC4 · AC5 · AC6 |

`docs/architecture.md` (root) has **zero** hits and needs no edit. `docs/general/*` carry no frontmatter.

Design to describe: narration events carry an optional vector plus the encoding model's name, index over narration
only, embedding inside the one transcript writer, its tokens and cost on the same row, a failure logged and the row
still written (sprint 01, on a parallel branch); search by meaning across the run and a recent-N recap (sprint 02).

## Work items

Three files never touched by two agents. WI1-WI3 run in parallel; WI4 is the closing read.

- **WI1** `claude` — `docs/general/model.md`: AC1, AC2, plus the `## The entities` sweep (`:34`, `:42`, `:45`).
- **WI2** `claude` — `docs/general/glossary.md`, `architecture.md`, `requirement-map.md`: AC3, AC4, AC5.
- **WI3** `claude` — `docs/intents/005-game-state-services/decisions/mechanics.md`: AC6, two lines plus `updated:`.
- **WI4** `claude` — run the AC7 grep, confirm every surviving hit is a rejected-or-Stage-02 mention, and confirm the
  five sentences below read the same in every file. Read-only; no qa agent, no test run.

## Interfaces

Wording the work items must agree on verbatim in substance:

1. **The one sentence (WI1, `model.md`)**: *The DM's long-term memory is its own past narration — every narration
   line is encoded as it is written and searched by meaning across the whole campaign run, across adventures.*
   WI2's Event clause (`glossary.md`) is the one-clause echo of it; no other file restates it.
2. **Tool name and description (WI2 + WI3, identical)**: `recall(query)` — *long-term memory: searches the run's past
   narration by meaning.* No `add_journal_entry`, no `search_journal`, no `record_fact`, no "journal write" anywhere.
3. **Recap is not a tool.** The most-recent-N recap is handed to the DM up front when a run resumes as a new chat
   (← D3); it appears in `model.md` prose only, never in the tool table (WI2) or the reads line (WI3).
4. **Scope and asymmetry**: the run, across adventures (← D5); only DM narration is encoded, never the player's typed
   text, which stays verbatim in the timeline (← D2).
5. **Failure**: an encoding failure is logged, the narration is written and shown as usual, and only that one line is
   not findable later — the player notices nothing (← D4). WI1 states it; no other file repeats it.
6. **Known gap 1 (WI1, `:193` and `:343` must match)**: a narration line that was true can still come back as a hit
   after it stopped being true; contained by the recent turns already in the chat history and by hard canon — hit
   points, position, inventory, scene — living on objects and read by tool, never by search.

## Open questions

- Technical: `recall` ships only in sprint 02, not yet built. Assumed answer — both docs are design contracts
  (`model.md:5-6`), so present tense, no Stage-02 marker; that marker stays reserved for `start_combat()`.
- Technical: the 005 attachment is human-owned and approved; the brief authorises these two lines explicitly. If
  that is not the intent, WI3 drops out and AC6/AC7 fail.
- None product-visible: nothing a player can see changes.
