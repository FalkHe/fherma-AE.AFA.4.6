---
author: fhit:architect
owner: human
created: 2026-09-22
stage: approved
---
# Sprint 05: the creation conversation over the network

## Task
Put the character module's agent behind HTTP for the web page to use: one authenticated write that starts
a conversation for a run and one that sends a single player message and answers with the Tavern Keeper's
reply, the sheet so far, the step the player is on, and whether the sheet is ready to save. Saving reuses
the character write of sprint 02. Regenerate the committed typed API client.

## Outcome
On the interactive API page a signed-in player can start a conversation, send three messages and watch the
sheet in the answer fill up, then save the character to the run.

## Acceptance criteria
- AC1: Starting a conversation for a run answers the greeting, and a run that already has a character is
  refused with the standard error envelope (← D9).
- AC2: One message in, one reply out — no streaming, no partial tokens, the whole reply in the response
  (← D3).
- AC3: Every reply carries the sheet so far, the step reached and whether it can be saved, so no second
  read is needed to draw the panel (← D14).
- AC4: Anonymous callers and players who are not members of the run are refused; a failing model answers
  the in-voice error line rather than a raw failure (← D16).
- AC5: A conversation nobody finishes leaves no character and no trace the run screen shows (← D12).
- AC6: The client is regenerated and committed; black-box acceptance tests cover the start, a message and
  the refusals.

## Decisions
← D3, D9, D12, D14, D16

## Assumptions
- The conversation is identified by an opaque id the start call returns, kept only in the existing
  checkpointer; there is no listing of conversations and no resume after leaving.
- The routes live with the character module, mounted in the v1 router like the others.
- Save stays the existing character write; this sprint adds no second way to write a character.

## Out of scope
No page, no components, no wording beyond the error line · no streaming · no history read.
