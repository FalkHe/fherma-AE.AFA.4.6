---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-18
updated: 2026-09-18
stage: approved
---
# Decisions

One line each. `→ file` links an attachment in `decisions/`.

- D1: No journal in Stage 01. Least effort is the goal: the DM's long-term memory is the narration it already wrote,
  made searchable by meaning — each narration event is encoded on write and the DM can search past narration on
  demand. No separate fact store, no fact event type, no DM writing tool; the play screen reloads from events alone.
  If a curated journal turns out to be a need, it is added in Stage 02.
- D2: Only the DM's narration is encoded for recall, never the player's typed text. The player's intent reaches memory
  because narration always acknowledges what the player did, in the adventure's tone — one instruction in the DM's
  prompt (phase 8), not a rephrase step. The raw player text stays verbatim in the timeline; blocking inappropriate
  text or injections is the phase 8 guard's job.
- D3: A play session is a persistent LLM chat. In a running session the DM recalls past narration on demand only,
  through its search tool. When a session is restored or continued as a new LLM chat, the DM is deliberately given a
  recap up front: the most recent narration of the run, by recency, since there is no player action yet to match on.
  Whether reopening a run continues the old chat or starts a new one is phase 8's call; the recap applies only to the
  new-chat case.
- D4: If encoding a narration line fails mid-turn, the turn carries on: the narration is written and shown as usual,
  and only that line is not findable by meaning later. The player notices nothing. A background job that re-encodes
  the missed lines can come in Stage 02 if this happens a lot.
- D5: The DM's search reaches the whole campaign run, across adventures — a run is one story, and remembering an NPC
  met two adventures ago is the point of long-term memory.
