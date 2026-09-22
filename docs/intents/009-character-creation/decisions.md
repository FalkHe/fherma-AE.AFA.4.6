---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-22
updated: 2026-09-22
stage: approved
---
# Decisions

One sentence each, in the product owner's words. `→ file` links an attachment in `decisions/`.

- D1: Character creation is its own character module; SRD facts (races, classes, their numbers) are hard-coded as data there, and the player is guided from free text to those facts wherever a rule needs a fixed value.
- D2: The creation agent is a dedicated agent living inside the character module, separate from the Dungeon Master.
- D3: The terminal chat ships first, the web chat afterwards; no token streaming for now.
- D4: All 9 SRD races and 12 SRD classes are offered.
- D5: Ability scores use point buy; the agent may offer a set fitting the class, or dice rolled by the game, never by the model.
- D6: Backgrounds are free-hand: the player tells the story, the agent asks when missing; no fixed SRD background list. Sourcebooks (Monster Manual, DMG) may later serve as guidelines, not hard facts.
- D7: A free-hand background grants two skill proficiencies from the SRD skill list; the agent suggests two that fit the story, the player chooses.
- D8: Starting equipment follows the class's SRD list; each either/or choice is offered in chat, with the class default as a one-turn "just the default".
- D9: Before saving, the player reviews a full sheet summary and confirms; once saved the character is final for Stage-01; an edit mode may come later.
- D10: The player tells name, looks and backstory in their own words; the agent rewrites them in the story's tone, and the review shows the rewrite.
- D11: The ready-made campaign character stays as a skip offered by the agent when creation starts.
- D12: An abandoned creation chat behaves whichever way costs the least technical effort; the agent's call, listed under the research assumptions.
- D13: The agent asks for the alignment (one of the nine SRD alignments), suggesting one from the backstory; the player confirms or picks another.
- D14: The web chat is a full page with a live "your sheet so far" panel and step indicator, following the delivered flow, review screen and character card; "View sheet" is dropped → decisions/D14-creation-chat-flow.md.
- D15: The creation agent presents itself as "Tavern Keeper" in its prompt and on screen only; the name appears nowhere in code or identifiers.
- D16: Wording follows the attachment and is in-voice everywhere, error lines included ("The tavern is noisy, I did not catch that. Say it again?"); "Create character" stays; the ready-made offer names the character; review buttons "Looks right, save" / "Change something" → decisions/D14-creation-chat-flow.md.
- D17: Picked starting equipment becomes real carried items that fight and count towards armour class, not text on the sheet (added at backlog, 2026-09-22).
- D18: Class-granted skill proficiencies are auto-filled in SRD order; only the two story skills are asked (least effort, added at backlog).
