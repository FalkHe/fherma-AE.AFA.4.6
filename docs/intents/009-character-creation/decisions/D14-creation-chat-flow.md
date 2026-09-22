---
author: ux-designer
owner: human
created: 2026-09-22
updated: 2026-09-22
stage: approved
---
# D14 — Character creation chat: flow, screens and wording

Decided 2026-09-22: alternative (a), the full page, is adopted (D14). Section 2 (b) is kept for the record.
Wording is dark-only "The Goblin's Tavern" tone, matching the run screen ("Waiting on party",
"Be brave, this feature is in development.").

## 1. Flow

1. On the run screen the player's own card reads "No character yet" and carries **Create character**; clicking it opens the creation chat (in the web, where it lives is the choice in section 2).
2. The agent greets in the campaign's tone, says what the next minutes will be, and offers two ways out of the gate: build your own, or take the ready-made hero of this campaign — the ready-made option is named with the character's name so the player knows what they are taking.
3. Ready-made path: the player accepts; the agent shows the same sheet summary as step 12 read-only, the player confirms, the character is saved and the chat closes — no further questions.
4. Build path: the player describes the character in free words ("a sneaky halfling burglar"); the agent turns that into fixed facts — race and class from the 9 SRD races and 12 SRD classes — and asks for a yes before writing them down.
5. If the free text does not name a race or class, the agent asks the missing one with two or three fitting suggestions plus "show me all of them"; asking for the full list prints them grouped, short line each.
6. Ability scores: the agent explains point buy in one sentence and offers three ways — "suggest a set for my class", "roll for me" (the game rolls, never the agent), or "I'll spend the points myself"; spending by hand is a guided back-and-forth with the remaining points shown after every change.
7. Backstory: the player tells name, looks and story in their own words, in any order and any length; the agent asks only for what is still missing.
8. The agent reads the story back in the campaign's tone — name, a few lines of looks, a short backstory — and asks whether that fits; the player can correct it in free words any number of times.
9. From the story the agent proposes two skill proficiencies with a one-line reason each; the player takes them or names two others from the SRD skill list.
10. From the story the agent proposes one of the nine alignments with a one-line reason; the player confirms or names another.
11. Equipment: the agent walks the class's either/or choices one at a time, each with a plain-words hint at what the option is good for; at any point "just the default" takes every remaining default in one turn.
12. Review: the full sheet appears as a summary — name, race, class, level 1, alignment, hit points, armour class, abilities with modifiers, proficiencies, equipment, looks, backstory — with **Looks right, save** and **Change something**.
13. "Change something" sends the player back into the chat: they name what should change in free words, the agent changes only that and shows the summary again.
14. On save, the chat closes and the run screen returns; the player card now shows the character card of section 4, the party line reads "1 of 1 characters ready", and the first adventure flips from "Waiting on party" to "Next up".
15. A saved character is final for now — the character card carries no edit affordance; if one is asked for it says the sheet is fixed for this run.
16. Leaving mid-way (closing the chat, navigating away, quitting the terminal) keeps nothing: the run screen still reads "No character yet" and a fresh **Create character** starts the conversation from the greeting. The confirmation on leaving is a short dialog: "Leave character creation? Nothing is kept — you would start over." with **Keep going** / **Leave**.
17. An error mid-chat (the agent cannot answer) shows an inline line in the transcript — "The tavern is noisy, I did not catch that. Say it again?" — with a **Try again** affordance (D16: in-voice everywhere); the conversation so far stays on screen, only the last turn is lost.

## 2. Where the web chat lives — two alternatives

### (a) Full page with a live sheet-in-progress side panel

```
┌────────────────────────────────────────────────────────────────────────────┐
│ THE GOBLIN'S TAVERN                                            (○) Falk    │
├────────────────────────────────────────────────────────────────────────────┤
│ ‹ The Sunless Citadel                                                      │
│                                                                            │
│ Create your character                        ┌───────────────────────────┐ │
│ Tell the tale. I'll keep the numbers.        │ YOUR SHEET SO FAR         │ │
│                                              ├───────────────────────────┤ │
│ ┌──────────────────────────────────────────┐ │ Name      Pip Underbough  │ │
│ │ ▸ Tavern Keeper                    │ │ Race      Halfling        │ │
│ │   Well met. Before we begin — this       │ │ Class     Rogue · Level 1 │ │
│ │   campaign keeps a hero ready: Alard...  │ │ Alignment —               │ │
│ │                                          │ │                           │ │
│ │                          you ◂ │ │ Abilities      not set yet│ │
│ │            a sneaky halfling burglar     │ │ STR — DEX — CON —         │ │
│ │                                          │ │ INT — WIS — CHA —         │ │
│ │ ▸ Tavern Keeper                    │ │                           │ │
│ │   A halfling rogue, then. Light feet,    │ │ Hit points   —            │ │
│ │   lighter fingers. Shall I write that    │ │ Armour class —            │ │
│ │   down?                                  │ │                           │ │
│ │                                          │ │ Skills       —            │ │
│ │   [ Yes, that's me ]  [ Not quite ]      │ │ Equipment    —            │ │
│ │                                          │ │                           │ │
│ │                                          │ │ ▓▓▓▓▓░░░░░  step 2 of 7   │ │
│ └──────────────────────────────────────────┘ └───────────────────────────┘ │
│ ┌──────────────────────────────────────────┐                               │
│ │ Say what you like…                [Send] │                               │
│ └──────────────────────────────────────────┘                               │
│                                              Leave creation                │
└────────────────────────────────────────────────────────────────────────────┘
```

On a narrow screen the panel moves under the composer as a collapsed strip:
`Halfling Rogue · Level 1 · step 2 of 7   ⌄` which expands into the same list.

### (b) Chat drawer over the run screen

```
┌────────────────────────────────────────────────────────────────────────────┐
│ THE GOBLIN'S TAVERN                                            (○) Falk    │
├────────────────────────────────────────────────────────────────────────────┤
│ ‹ Campaigns                        ░░│ Create your character          [×] │
│                                    ░░├────────────────────────────────────┤
│  [In progress]                     ░░│ ▸ Tavern Keeper              │
│  The Sunless Citadel               ░░│   Well met. Before we begin —      │
│  A ruined fortress swallowed by…   ░░│   this campaign keeps a hero       │
│                                    ░░│   ready: Alard the Steady, a       │
│  PARTY   0 of 1 characters ready   ░░│   human fighter. Take him, or      │
│  ┌──────────────────────────┐      ░░│   shall we make someone of your    │
│  │ F  Falk        (owner)   │      ░░│   own?                             │
│  │    falk@hermann.pm       │      ░░│                                    │
│  │    ┌──────────────────┐  │      ░░│   [ Take Alard ]  [ Make my own ]  │
│  │    │ Creating…        │  │      ░░│                                    │
│  │    └──────────────────┘  │      ░░│                     you ◂ │
│  └──────────────────────────┘      ░░│       a sneaky halfling burglar    │
│                                    ░░│                                    │
│  ADVENTURES                        ░░│ ▸ Tavern Keeper              │
│  1  The Old Road   Waiting on party░░│   A halfling rogue, then. Shall I  │
│                                    ░░│   write that down?                 │
│                                    ░░├────────────────────────────────────┤
│                                    ░░│ Say what you like…          [Send] │
└────────────────────────────────────────────────────────────────────────────┘
```

The sheet-in-progress does not fit beside the transcript here; it becomes a collapsible
header strip inside the drawer (`Halfling Rogue · step 2 of 7 ⌄`).

**Recommendation: (a), the full page.** Creation is a five-to-ten-minute conversation with a
dozen decisions, not a side errand — it deserves the whole screen, and the run screen behind a
drawer is scenery the player cannot use anyway. The live sheet is what makes the chat feel
trustworthy: the player watches free words turn into fixed numbers, sees what is still empty,
and reaches the review with no surprises; in a drawer that panel collapses into a strip and the
reassurance is gone. The full page is also the same shape on phone and desktop and is the shape
the play screen will need later, so the pattern is built once. The drawer's only real advantage
— never losing the run screen — is worth little when leaving mid-way discards the work anyway.

## 3. Review, confirm, and the finished character

### Review and confirm

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ‹ The Sunless Citadel                                                      │
│                                                                            │
│  One last look                                                             │
│  This is who walks into the tavern. Saving makes it final for this run.     │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  PIP UNDERBOUGH                                                      │  │
│  │  Halfling Rogue · Level 1 · Chaotic Good                             │  │
│  │                                                                      │  │
│  │  Hit points 9        Armour class 14        Speed 25 ft              │  │
│  │                                                                      │  │
│  │  ABILITIES                                                           │  │
│  │  STR  8  (−1)   DEX 16 (+3)   CON 14 (+2)                            │  │
│  │  INT 12  (+1)   WIS 10 (+0)   CHA 13 (+1)                            │  │
│  │                                                                      │  │
│  │  SKILLS      Stealth, Sleight of Hand, Perception, Deception         │  │
│  │              (Stealth and Sleight of Hand come from your story)      │  │
│  │                                                                      │  │
│  │  EQUIPMENT   Rapier · Shortbow and 20 arrows · Burglar's pack        │  │
│  │              Leather armour · Two daggers · Thieves' tools           │  │
│  │                                                                      │  │
│  │  LOOKS       Barely three feet of him, all elbows and grin. Curly    │  │
│  │              black hair, a nose broken twice, and boots so quiet     │  │
│  │              the floorboards forget he stood on them.                │  │
│  │                                                                      │  │
│  │  STORY       Raised in the kitchens of a river inn, Pip learned      │  │
│  │              that a full purse travels badly and a light one         │  │
│  │              travels far. He left the night the innkeeper counted.   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  [ Looks right, save ]   [ Change something ]                              │
└────────────────────────────────────────────────────────────────────────────┘
```

### The character card on the run screen afterwards

```
│  PARTY                                      1 of 1 characters ready        │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  F   Falk                                                    (owner) │  │
│  │      falk@hermann.pm                                                 │  │
│  │  ┌────────────────────────────────────────────────────────────────┐  │  │
│  │  │  🜂  PIP UNDERBOUGH                                 ● Ready    │  │  │
│  │  │     Halfling Rogue · Level 1                                   │  │  │
│  │  │     HP 9    AC 14                                              │  │  │
│  │  │                                                                │  │  │
│  │  │     Barely three feet of him, all elbows and grin. Curly       │  │  │
│  │  │     black hair, a nose broken twice, and boots so quiet the    │  │  │
│  │  │     floorboards forget he stood on them.                       │  │  │
│  │  └────────────────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ADVENTURES                                                                │
│  1   The Old Road                     Next up        [ Start adventure ]   │
```

The looks text clamps to three lines with an ellipsis. The card stands on its own; a read-only
"View sheet" was proposed and dropped (D14).

## 4. Sample terminal transcript

```
The Goblin's Tavern — character creation
Campaign: The Sunless Citadel

Keeper  Well met. You'll need someone to send into that hole in the ground.
        This campaign keeps a hero ready — Alard the Steady, a human fighter,
        sword already sharpened. Say "take Alard" and you're at the table.
        Otherwise, tell me who you'd rather be. Anything goes; I'll sort out
        the rules as we talk. ("help" for what I can do, "quit" to walk out.)

you     a sneaky halfling burglar

Keeper  A halfling rogue, then — light feet and lighter fingers. That fixes
        two things: Halfling (small, quick, hard to frighten) and Rogue
        (sneaking, locks, and hitting where it hurts). Sound right? [y/n]

you     y

Keeper  Written down. Now the numbers. You get a pool of points to spend
        across six abilities — or I can suggest a set that suits a rogue,
        or let the dice decide. Which shall it be?
        1) suggest a set   2) roll for me   3) I'll spend them myself

…

Keeper  That's everyone. Here's Pip Underbough, Halfling Rogue, Level 1,
        Chaotic Good — HP 9, AC 14, rapier at his hip. Full sheet above.
        Save him as he stands? Saving is final for this run.
        [s]ave · [c]hange something · [q]uit without saving
```

## 5. Wording points

All settled by D15 and D16: agent name "Tavern Keeper"; "Create character" stays; the ready-made offer names the character; "Looks right, save" / "Change something"; leave dialog "Leave character creation? Nothing is kept, you would start over." with "Keep going" / "Leave"; errors stay in-voice ("The tavern is noisy, I did not catch that. Say it again?"); every string is in the tavern's voice; "Waiting on party" / "Next up" stay as shipped.
