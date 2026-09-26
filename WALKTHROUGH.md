# Goblins of Greenhollow — mechanics walkthrough

A short route through the first adventure that shows the four core mechanics
in the narration stream: an item changing hands, a scene exit, a player
ability check with the **Roll** button, and a fight with initiative, attack
and damage rolls. It was played end to end on the hosted app; results and
prose vary from run to run, the mechanics do not.

## Setup

1. Sign in (or create an account), press **Create new campaign** and pick **Greenhollow**.
2. On the campaign page press **Create character**, then **Take Rosalind Thorn**
   and **Looks right, save**. Rosalind is a Human Fighter, HP 12, AC 15. Her
   pack holds a wooden shield, a hooded lantern, twine and rations — **no
   weapon**. The shepherd's knife is behind Mira's bar.
3. Press **Start adventure**. The opening narration places you on the village
   green with Mira, the barrel and the knife.

Paste **one message at a time** into *What do you do?* and wait for the
Dungeon Master's reply. When a **Roll** button appears, press it; the game
rolls, never the storyteller. Every mechanic below leaves its own line in the
stream between your message and the narration.

## 1. Give — the knife changes hands

```text
I approach Mira at the barrel. I will go north after the raiders. Please give me the shepherd's knife from behind the bar.
```

What you see: a centred line `· Mira gives the Shepherd's Knife to Rosalind
Thorn ·`, then the narration of the handover. The item moved from Mira's
inventory to Rosalind's through the `give` operation; the narration was
written afterwards from that recorded fact.

## 2. Exit — leaving the village green

```text
I take the cart track north toward the Thornway.
```

What you see: a new scene heading **The Thornway** above the Dungeon Master's
reply. The `use_exit` operation changed the scene; the page subtitle follows.

Wording matters here: sentences with movement verbs (*go, follow, head,
walk, enter, climb…*) are read as a move. The next step must therefore
search **without** walking anywhere.

## 3. Ability check — a Wisdom (Perception) roll

At the Thornway fork, search on the spot:

```text
Staying where I am, I crouch and carefully search the wool tufts and the thorn stems at ankle height for signs of passage.
```

What you see: a line `· wisdom (Perception) · DC 5 ·` and a **Roll 1d20**
button. Press it. A dice chip shows the die, the total and *Made it* or
*Missed it*, and the narration describes what Rosalind noticed (or did not).
The Thornway check is easy on purpose; a second, harder one (DC 14) waits at
the Lair Maw if you scan the rock face for another way in.

Then continue along the wool-marked cut:

```text
I continue along the wool-marked narrow cut to the rocky outcrop.
```

The heading changes to **The Lair Maw**: three goblin watchers sit above a
thorn-screened cave mouth.

## 4. Combat — initiative, attack, damage

```text
I attack the nearest goblin watcher with my shepherd's knife.
```

What you see, in order:

- `· Initiative ·` with a **Roll 1d20+1** button: press it. Your chip and the
  goblins' initiative chip appear.
- Each goblin acts once. A hit shows as `· Rosalind Thorn: 12 → 9 hit
  points ·`; a miss just narrates.
- On Rosalind's turn her **attack** appears as a chip `· Attack ·` with the
  knife's formula (1d20+4), the die and the total; the game rolls it for her.
  A hit is followed by a **damage** roll and the goblin's hit-point line, a
  miss by narration.
- Repeat the attack message on your turns until a watcher falls. Three
  goblins against a level-1 fighter is a hard fight: should Rosalind reach
  0 hit points, the stream shows *The adventure ends in defeat.*, the
  composer closes and a link leads back to the campaign.

Every roll in this fight is a recorded event; the Dungeon Master only chose
*who attacks whom* and wrote the prose from the results.

## Beyond the four

The same route continues into the lair: lift the thorn screen (a DC 13
fixture interaction, or cut the lashings with the knife and skip the roll),
descend the scree, fight Grettle and her bodyguard, open the wool sack
(DC 8), take the two fleeces and leave by the scree slope, which ends the
adventure. Greenhollow authors no saving throw, passive check or custom roll,
so this walkthrough does not invent one.

| Mechanic | Where this route shows it |
|---|---|
| Item give / take / drop | Step 1 (the horseshoe on the barrel can also be taken and dropped) |
| Scene and adventure exits | Step 2, the cut to the Lair Maw, the scree, the final slope |
| Player ability check with Roll button | Step 3 (DC 5 and DC 14), the thorn screen, the wool sack |
| Initiative, attack, damage, hit points | Step 4 and the hollow |
| Hidden DM rolls and monster actions | The goblins' attacks in step 4 |
| Rule lookup and campaign memory | Ask the Dungeon Master to explain an SRD rule, or what Mira said |
