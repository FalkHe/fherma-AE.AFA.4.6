---
author: ux-designer
owner: human
created: 2026-09-22
updated: 2026-09-22
stage: approved
---
# D12 — The play screen: flow, states and wording

Designed inside D1–D11. Voice is the same tavern register as character creation
(D14/D16 of intent 009): the Dungeon Master speaks, error lines included, and
nothing on screen speaks like software. Names in the wireframes are the real
Greenhollow content — campaign "Greenhollow", adventure "Goblins of Greenhollow",
scene "The Village Green", the campaign's ready-made hero Rosalind Thorn.

## 1. Flow

**Entering**

1. On the run screen the current adventure carries **Start adventure**; once it
   has been played it reads **Continue**. Either one opens the play screen; the
   run screen stays the lobby and the header's back link returns to it (D1).
2. The ready-made hero is enough — nothing on the play screen asks for a
   character (D9).
3. A brand-new adventure opens with the scene name, an empty transcript and the
   opening turn already running: the Dungeon Master reads the adventure in and
   describes the first scene, and that narration arrives in one piece like any
   other (D3). Until it lands the transcript carries only its empty line.
4. Returning to an adventure already under way opens on the recorded transcript,
   scrolled to the newest entry (D6).

**Taking a turn**

5. The composer asks "What do you do?"; the player writes in free words and sends.
6. The player's words appear in the transcript at once under the character's
   name, and the composer closes for the length of the turn.
7. "The Dungeon Master is thinking…" sits at the foot of the transcript while the
   turn runs (D3).
8. Everything the Dungeon Master does appears as it happens, between the
   narration: a small line for a rule looked up, a small line for anything that
   changed in the world, the check being called for, and the dice themselves
   (D10). The closing narration arrives whole, at the end.
9. A roll the game makes on its own — the Dungeon Master calls it, the dice fall,
   no button — simply appears in the transcript as a dice result.
10. The party rail follows along: hit points and armour class change as the rolls
    that changed them land (D7).
11. When the scene changes, a divider with the new scene's name closes the old one
    and the header's second line changes with it.

**Answering**

12. When the turn stops on a question, the question stands in the transcript with
    its answers as buttons underneath, and the composer is closed: only those
    buttons work until one is picked (D2).
13. When the turn stops on a roll, the check and its difficulty stand in the
    transcript and a single **Roll** button waits beneath. The game rolls; the
    player never types a number and the Dungeon Master never invents one (D2).
14. Picking an answer or rolling writes the result into the transcript and the
    same turn continues from there — the thinking line returns.
15. The composer opens again the moment the turn is finished and nothing is
    pending (D2).

**When it takes too long, or breaks**

16. At about 45 seconds the thinking line admits it: the turn is a long one and
    the game is still waiting (D5).
17. At about 2 minutes, and on any turn that breaks halfway, the waiting ends in
    one line in the Dungeon Master's voice carrying **Try again** (D4, D5).
18. Everything recorded before the break stays on screen and counts: a roll that
    already fell is not rolled again, a question already answered is not asked
    again. **Try again** picks the turn up from there. The composer opens too —
    a lost narration only means acting again (D4, D6).

**Leaving and coming back**

19. The back link leaves for the lobby with no warning and no confirmation:
    everything recorded is kept, so there is nothing to lose (D6).
20. Coming back — by **Continue** on the run screen — shows everything that was
    recorded. A question or a roll left pending is still standing there, waiting
    for the same button. A turn that was in flight and never finished shows the
    failure line with **Try again** (D6).

**Ending**

21. When the adventure ends, the Dungeon Master narrates the ending as the last
    entry, a marker closes the transcript beneath it, the composer is gone and a
    single button leads back to the lobby (D11).

## 2. The screen at rest

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ THE GOBLIN'S TAVERN                                                (○) Falk  │
├──────────────────────────────────────────────────────────────────────────────┤
│ ‹ Greenhollow                                    ┌─────────────────────────┐ │
│ Goblins of Greenhollow                           │ PARTY                   │ │
│ The Village Green · saved as you go              ├─────────────────────────┤ │
│                                                  │ 🜂 ROSALIND THORN       │ │
│ ┌──────────────────────────────────────────────┐ │    Human Fighter · Lvl 1│ │
│ │ ───────────  The Village Green  ───────────  │ │                         │ │
│ │                                              │ │    HP   12 / 12         │ │
│ │ ▸ The Dungeon Master                   21:02 │ │    AC   15              │ │
│ │   Greenhollow is a dozen houses round a      │ └─────────────────────────┘ │
│ │   well, and every door on the green is shut. │                             │
│ │   Mira has laid a torn grain sack and a bent │                             │
│ │   horseshoe on a barrel, and waits for you   │                             │
│ │   to look at them.                           │                             │
│ │                                              │                             │
│ │                    Rosalind Thorn ◂    21:04 │                             │
│ │         I pick up the horseshoe and ask Mira │                             │
│ │         who found it.                        │                             │
│ │                                              │                             │
│ │       · Checked the rules · Investigation ·  │                             │
│ │       · Intelligence (Investigation) · DC 12 │                             │
│ │                                              │                             │
│ │        ┌───────────────────────────────┐     │                             │
│ │        │ Investigation        1d20+1   │     │                             │
│ │        │ 13 + 1                  14 ✓  │     │                             │
│ │        └───────────────────────────────┘     │                             │
│ │                                              │                             │
│ │       · Rosalind Thorn takes the Bent        │                             │
│ │         Horseshoe ·                          │                             │
│ │                                              │                             │
│ │ ▸ The Dungeon Master                   21:05 │                             │
│ │   The shoe was wrenched out of true by       │                             │
│ │   something heavier than the horse that wore │                             │
│ │   it. Mira watches you turn it over and says │                             │
│ │   nothing, which is answer enough.           │                             │
│ └──────────────────────────────────────────────┘                             │
│ ┌──────────────────────────────────────────────┐                             │
│ │ What do you do?                       [Send] │                             │
│ └──────────────────────────────────────────────┘                             │
└──────────────────────────────────────────────────────────────────────────────┘
```

Four kinds of row, and no others: the Dungeon Master's narration (left, named,
timed), the player's words (right, under the character's name), a small system
line (centred, between dots, one line, never wrapped into a paragraph), and a
dice result (centred chip). Scene dividers separate scenes. The transcript keeps
itself at the newest entry; scrolling up puts a **Jump to the latest** pill at
the foot of it until the player scrolls back down.

The header identifies all three things at once: the back link names the run, the
title names the adventure, the second line names the scene the party is standing
in and reassures that nothing needs saving.

There is no developer drawer and no placeholder for one (D8).

## 3. The states

### Turn in flight

```
│ │                    Rosalind Thorn ◂    21:06 │
│ │      I follow the wool tufts north into the  │
│ │      thorn.                                  │
│ │                                              │
│ │   ◌ The Dungeon Master is thinking…          │
│ └──────────────────────────────────────────────┘
│ ┌──────────────────────────────────────────────┐
│ │ The Dungeon Master has the floor.            │
│ └──────────────────────────────────────────────┘
```

Composer closed, nothing to click. Everything the turn does appears above the
thinking line as it happens; the thinking line stays at the foot until the turn
is finished.

### Waiting on a choice

```
│ │ ▸ The Dungeon Master                   21:07 │
│ │   Mira catches your sleeve at the gate. "The │
│ │   knife went north with the shepherd and     │
│ │   came back without him. Take it?"           │
│ │                                              │
│ │   [ Take the knife ]  [ Leave it with Mira ] │
│ │   [ Ask where it was found ]                 │
│ └──────────────────────────────────────────────┘
│ ┌──────────────────────────────────────────────┐
│ │ The Dungeon Master is waiting on one of those.│
│ └──────────────────────────────────────────────┘
```

Only the buttons work. The picked answer is written into the transcript as the
player's own row and the turn goes on from there.

### Waiting on a roll

```
│ │ ▸ The Dungeon Master                   21:09 │
│ │   The thornbrush is lashed thick across the  │
│ │   cave mouth. Lifting it aside quietly will  │
│ │   take a steady hand.                        │
│ │                                              │
│ │       · Dexterity (Stealth) · DC 13 ·        │
│ │                                              │
│ │              [ Roll 1d20+3 ]                 │
│ └──────────────────────────────────────────────┘
│ ┌──────────────────────────────────────────────┐
│ │ The dice go first.                           │
│ └──────────────────────────────────────────────┘
```

One button, and it says what is being rolled. Pressing it replaces the button
with the dice chip and the turn continues.

### The long wait (~45 s)

```
│ │   ◌ Still thinking. This one is taking its   │
│ │     time — nothing is lost, the Dungeon      │
│ │     Master is still at it.                   │
```

Same place, same spinner, only the words change. Nothing else on screen moves.

### The turn that broke (and the 2-minute give-up)

```
│ │       · Dexterity (Stealth) · DC 13 ·        │
│ │        ┌───────────────────────────────┐     │
│ │        │ Stealth              1d20+3   │     │
│ │        │ 14 + 3                  17 ✓  │     │
│ │        └───────────────────────────────┘     │
│ │                                              │
│ │ ▸ The Dungeon Master                   21:11 │
│ │   The Dungeon Master has lost the thread of  │
│ │   that one. Nothing that already happened is │
│ │   lost — shall we pick it up again?          │
│ │                                              │
│ │              [ Try again ]                   │
│ └──────────────────────────────────────────────┘
│ ┌──────────────────────────────────────────────┐
│ │ What do you do?                       [Send] │
│ └──────────────────────────────────────────────┘
```

The roll that already fell stays and still counts. Both ways out are open: pick
the same turn up with **Try again**, or simply do something else.

### The adventure ended

```
│ │ ▸ The Dungeon Master                   22:40 │
│ │   Grettle's cloak goes back to the household │
│ │   it was cut from, the fleeces go back to    │
│ │   the green, and Mira keeps the door open    │
│ │   long past closing. Greenhollow sleeps      │
│ │   through the night for the first time in a  │
│ │   month.                                     │
│ │                                              │
│ │ ══════  Here ends Goblins of Greenhollow  ═══│
│ │                                              │
│ │           [ Back to Greenhollow ]            │
│ └──────────────────────────────────────────────┘
```

No composer at all — the transcript is closed and the only way on is the button,
which returns to the lobby (D11). Coming back to a finished adventure later shows
exactly this: the whole transcript, the marker, the button.

### First entry into a brand-new adventure

```
│ ‹ Greenhollow                                    ┌─────────────────────────┐ │
│ Goblins of Greenhollow                           │ PARTY                   │ │
│ The Village Green · saved as you go              ├─────────────────────────┤ │
│                                                  │ 🜂 ROSALIND THORN       │ │
│ ┌──────────────────────────────────────────────┐ │    Human Fighter · Lvl 1│ │
│ │ ───────────  The Village Green  ───────────  │ │    HP   12 / 12         │ │
│ │                                              │ │    AC   15              │ │
│ │   Nothing written down yet. The Dungeon      │ └─────────────────────────┘ │
│ │   Master is opening the book.                │                             │
│ │                                              │                             │
│ │   ◌ The Dungeon Master is thinking…          │                             │
│ └──────────────────────────────────────────────┘                             │
│ ┌──────────────────────────────────────────────┐                             │
│ │ The Dungeon Master has the floor.            │                             │
│ └──────────────────────────────────────────────┘                             │
```

The scene name and the party rail are there from the first paint; only the
transcript is empty, and only until the opening narration lands.

## 4. Every string

| Where | Text |
|---|---|
| Back link (to the lobby) | `‹ {campaign}` — e.g. "‹ Greenhollow" |
| Header title | `{adventure}` — e.g. "Goblins of Greenhollow" |
| Header second line | `{scene} · saved as you go` |
| Scene divider | `{scene}` |
| Party rail heading | "Party" |
| Party card lines | `{character name}` · `{race} {class} · Level {n}` · `HP {current} / {max}` · `AC {n}` |
| Narration row author | "The Dungeon Master" |
| Player row author | `{character name}` |
| Composer placeholder (open) | "What do you do?" |
| Composer send button | "Send" |
| Composer while a turn runs | "The Dungeon Master has the floor." |
| Composer while a choice waits | "The Dungeon Master is waiting on one of those." |
| Composer while a roll waits | "The dice go first." |
| Thinking line, first stage | "The Dungeon Master is thinking…" |
| Thinking line, after ~45 s | "Still thinking. This one is taking its time — nothing is lost, the Dungeon Master is still at it." |
| Roll button | `Roll {notation}` — e.g. "Roll 1d20+3" |
| Check called for | `{ability} ({skill}) · DC {n}` — e.g. "Dexterity (Stealth) · DC 13" |
| Dice chip | `{label}` · `{notation}` · `{breakdown}` · `{total}` · ✓ made it / ✗ missed |
| System line, rule lookup | `Checked the rules · {topic}` — e.g. "Checked the rules · Hiding" |
| System line, state change | `{who or what} {what changed}` — "Rosalind Thorn takes the Bent Horseshoe", "Rosalind Thorn: 12 → 9 hit points", "The screen of thornbrush is cut open" |
| Failure line (broken turn and the ~2 min give-up alike) | "The Dungeon Master has lost the thread of that one. Nothing that already happened is lost — shall we pick it up again?" |
| Retry button | "Try again" |
| Adventure end marker | `Here ends {adventure}` |
| Adventure end button | `Back to {campaign}` — e.g. "Back to Greenhollow" |
| Empty transcript, before the first turn | "Nothing written down yet. The Dungeon Master is opening the book." |
| Scrolled-up pill | "Jump to the latest" |
| Lobby: adventure already under way | badge "In progress", button "Continue" |
| Lobby: adventure finished | badge "Done", button "Read it back" |

Every one of these is the Dungeon Master's table talking, including the failure
line — the same rule as character creation (D16 of intent 009).

## 5. Narrow screens

Same screen, one change: the party rail leaves the right edge and becomes a
one-line strip pinned under the header — `Rosalind Thorn · HP 12/12 · AC 15 ⌄` —
which opens into the full card on tap, so hit points stay in sight while the
transcript scrolls under it.

```
┌────────────────────────────────────┐
│ ‹ Greenhollow                      │
│ Goblins of Greenhollow             │
│ The Village Green · saved as you go│
├────────────────────────────────────┤
│ Rosalind Thorn · HP 12/12 · AC 15 ⌄│
├────────────────────────────────────┤
│ ────── The Village Green ───────   │
│                                    │
│ ▸ The Dungeon Master         21:02 │
│   Greenhollow is a dozen houses    │
│   round a well, and every door on  │
│   the green is shut…               │
│                                    │
│           Rosalind Thorn ◂   21:04 │
│    I pick up the horseshoe.        │
│                                    │
│  · Checked the rules ·             │
│    Investigation ·                 │
│  ┌──────────────────────────────┐  │
│  │ Investigation      1d20+1    │  │
│  │ 13 + 1                14 ✓   │  │
│  └──────────────────────────────┘  │
├────────────────────────────────────┤
│ What do you do?             [Send] │
└────────────────────────────────────┘
```

Choice buttons stack full-width; everything else is the same screen.

## 6. Open — please confirm

1. **Does entering a new adventure cost a turn?** My default: yes — opening the
   adventure starts a Dungeon Master turn, so the player waits a few seconds on
   the empty transcript before the first narration. The alternative is to print
   the authored opening paragraph instantly and only then let the Dungeon Master
   take over; that is faster but the first thing the player reads is not the
   Dungeon Master reacting to them.
2. **Scene artwork.** The delivered design puts a picture at the top of the
   transcript for each scene. My default: no picture in this intent — the
   transcript starts at the scene divider, and the slot comes back when there is
   real artwork.
3. **What the party rail shows.** The design's card also carries initiative order
   and conditions ("Poisoned"). My default: hit points and armour class only (D7),
   since combat is not built yet; conditions appear as system lines in the
   transcript instead.
