---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/59
---
# Review: Sprint 05 — the creation conversation over the network

## What changed
The Tavern Keeper conversation can now be held over the network, one message at a time. Starting a conversation for a run answers the greeting; every message answers the Keeper's whole reply together with the sheet so far, the step the player is on, whether the sheet is ready to save and whether it was saved. Saving still happens inside the conversation when the player says yes. A model failure answers the in-voice line instead of a raw error. The typed web client knows the two new calls.

## How to check it
- On the interactive API page, signed in, start a conversation for a fresh run: the reply names Rosalind Thorn and the step reads race and class.
- Send "a sneaky halfling burglar", then "yes": the reply carries the Keeper's words, the sheet shows Halfling and Rogue, the step moves to scores; once scores are set the sheet's dexterity already includes the halfling's +2.
- Start a conversation on a run that already has a character: refused with the character-exists error.
- Signed out, the same call is refused; a message on a made-up conversation id is not found.

## Heads-up
- Conversations live in the server's memory only: a restart or a second server process forgets them and the player starts over, as decided for abandoned chats.
- The client was regenerated from the same export the usual target uses, but the usual target's web container would not start in the agent's sandbox (a name-resolution issue unrelated to this sprint); worth a quick `make generate-api` on your machine to confirm nothing differs.

Brief: docs/intents/009-character-creation/sprints/05-creation-chat-api/brief.md

## Verdict
Round 1: changes requested — the ability scores in the running sheet leave out the race's bonus, so a halfling rogue reads dexterity 15 while the armour class beside it, the Keeper's own review and the saved character all say 17; everything else checked out over the network.
Round 2: approve — the running sheet's ability scores now include the race's bonus and agree with the Keeper's review, the armour class beside them and the saved character; starting, holding and saving the conversation over the network all work, and the refusals still hold.
