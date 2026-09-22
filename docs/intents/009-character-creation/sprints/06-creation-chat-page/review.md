---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: –
---
# Review: Sprint 06 — the creation page

## What changed
"Create character" on the run screen now opens a page of its own where the player talks to the Tavern Keeper. The transcript shows both sides, offered choices appear as buttons that send exactly what typing them would ("Take Rosalind Thorn" or "Make my own" at the start, the three ways to set scores, "Just the default" for gear), and a "your sheet so far" panel beside the chat fills in as facts are fixed, with a step counter; on a narrow screen it collapses to a one-line strip. Leaving asks first, and a failed turn shows the tavern's error line with a retry that keeps the conversation on screen.

## How to check it
- Open a run without a character and click "Create character": the creation page opens at its own address, the Keeper's greeting names Rosalind Thorn, and two buttons offer taking her or making your own.
- Click "Make my own" and type "a sneaky halfling burglar": the sheet panel shows Halfling and Rogue after your yes, and the step counter advances.
- Narrow the window: the panel becomes a strip like "Halfling Rogue · Level 1 · step 2 of 7" that expands on click.
- Click "Back to the run": the dialog asks "Leave character creation? Nothing is kept, you would start over."; "Leave" returns to the run screen unchanged.
- Stop the model (a wrong key) and send a message: the tavern's line appears inline with "Try again".

## Heads-up
- The browser's Back button leaves without asking; only the page's own exit and closing the tab ask. Nothing is lost that leaving would not discard anyway.
- Reloading the page starts a fresh conversation, by decision.
- The review screen and the saved character card are sprint 07; on this page the conversation ends with the Keeper's save question.
- The reply now also carries the ready-made hero's name so the offer can be a button.

Brief: docs/intents/009-character-creation/sprints/06-creation-chat-page/brief.md

## Verdict
