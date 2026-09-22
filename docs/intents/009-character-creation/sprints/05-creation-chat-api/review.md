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
- Send "a sneaky halfling burglar", then "yes": the reply carries the Keeper's words, the sheet shows Halfling and Rogue, the step moves to scores.
- Start a conversation on a run that already has a character: refused with the character-exists error.
- Signed out, the same call is refused; a message on a made-up conversation id is not found.

## Heads-up
- Conversations live in the server's memory only: a restart or a second server process forgets them and the player starts over, as decided for abandoned chats.
- The client was regenerated from the same export the usual target uses, but the usual target's web container would not start in the agent's sandbox (a name-resolution issue unrelated to this sprint); worth a quick `make generate-api` on your machine to confirm nothing differs.

Brief: docs/intents/009-character-creation/sprints/05-creation-chat-api/brief.md

## Verdict
