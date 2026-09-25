# Goblins of Greenhollow — mechanics walkthrough

Start **Goblins of Greenhollow** as **Rosalind Thorn**. Paste **one code block at a time** into the play screen, after the DM finishes the previous turn. When the game offers a choice or a **Roll** button, use that control before pasting the next message. The DM decides when a check is needed; the game rolls the dice. Results and narration will vary.

Rosalind already carries a shepherd's knife in her starting inventory. Mira carries another, but the opening narration has **not** yet had Mira offer a job or speak to Rosalind. The first message starts that conversation.

This route follows the authored story and covers its available checks, fixture interactions, inventory moves, exits, combat, hit points, interruptions and adventure completion. Greenhollow does not author a saving throw, a passive check, or a custom player roll, so those mechanics are listed at the end rather than being invented as story events.

## The Village Green

1. **Talk to Mira** — conversation and DM narration; no roll is prescribed here.

   ```text
   I approach Mira at the barrel. What happened to the shepherd and the flocks, and what does the village need me to do?
   ```

2. **Examine and take the clue** — taking a placed item moves the bent horseshoe into inventory. Inspecting it may prompt further narration, but the adventure gives it no special check.

   ```text
   I examine the bent horseshoe on the barrel and take it with me as a clue.
   ```

3. **Drop and recover the clue** — dropping an item is a free inventory move. Pick the horseshoe up again before giving it to Mira.

   ```text
   I put the bent horseshoe down beside the barrel, then pick it up again.
   ```

4. **Return the clue** — giving an item to a creature in the same scene moves it out of inventory.

   ```text
   I give the bent horseshoe back to Mira. I have seen what I need from it.
   ```

5. **Agree and depart** — responds to Mira after speaking with her, then uses the cart-track exit to enter the Thornway. If the DM has not yet explained her request, finish that conversation first.

   ```text
   I will follow the missing flock's trail and find out what is raiding Greenhollow. I take the cart track north toward the Thornway.
   ```

## The Thornway

6. **Stop and search the trail** — the low wool tufts invite a closer look. This deliberate search calls for the hidden **Wisdom (Perception) DC 5** check; use the game's **Roll** button if offered. The result determines whether Rosalind notices how the cut was widened. It does not determine whether she may follow the wool-marked route.

   ```text
   I follow the wool tufts just into the narrow cut, then stop and crouch. I carefully search the ground and thorn stems at ankle height for signs of passage. Please call for a Wisdom (Perception) roll before I continue.
   ```

7. **Continue to the lair** — uses the exit that opens after following the wool-marked trail.

   ```text
   I continue along the wool-marked narrow cut to the rocky outcrop.
   ```

## The Lair Maw

8. **Search before approaching** — scanning the rock face can trigger the authored **Wisdom (Perception) DC 14** discovery of an unwatched side gap. The main entrance remains available regardless of the result. Three goblins watch from above; spotting a gap does not itself move Rosalind into the cave.

   ```text
   Before approaching the cave mouth, I scan the rock face for another way in and watch where the three goblins are looking.
   ```

9. **Open the main entrance quietly** — lifting the thorn screen branch by branch is an authored **DC 13 fixture interaction**. Let the DM call for and resolve the check. On failure, try again if the situation allows, or use the knife option below. Avoid claiming the goblins did not notice until the DM says so.

   ```text
   When the watchers look away, I lift the lashed thornbrush aside a branch at a time, keeping it from scraping the stone.
   ```

   **Optional knife bypass:** Rosalind's starting knife can cut the lashings without the screen's DC 10 check. This opens the cave mouth visibly to anything watching it. Use this instead of step 9, or after a failed attempt when possible.

   ```text
   I use my shepherd's knife to cut through the lashings holding the thornbrush screen together.
   ```

10. **Enter the cave** — uses the downward scree exit. If the watchers intervene, deal with them before moving on; their warning can change how prepared the hollow's defenders are.

   ```text
   I pass through the opening and descend the scree into the cave.
   ```

## The Lair Hollow

11. **Confront the defenders** — Grettle and one bodyguard are here. Combat can involve **initiative, attack rolls, damage rolls, armour class, and hit-point changes**. Paste an attack only when it is Rosalind's turn; repeat as needed, changing the target to match who is still present. The DM and game resolve every roll. Grettle may flee through the wall crack when the fight turns against her.

    ```text
    I attack Grettle with my shepherd's knife.
    ```

    ```text
    I attack the bodyguard goblin with my shepherd's knife.
    ```

12. **Open the wool sack** — working its knot by hand is an authored **DC 8 fixture interaction**. Do this when it is safe to reach the sack. If the check fails, try again if the DM permits.

    ```text
    I work the knotted neck of the hanging wool sack loose by hand.
    ```

13. **Recover the fleeces** — taking each of the two fleeces moves it into inventory. If the DM exposes them one at a time, repeat this message after the first is taken.

    ```text
    I take a stolen fleece from the open sack.
    ```

14. **Leave the hollow** — the scree-slope exit is the authored **adventure_end** exit. Leaving completes the adventure whether Grettle was defeated or escaped; her escape changes the story's outcome.

    ```text
    I climb back up the scree slope and leave the Thornway lair behind.
    ```

The discovered side gap is story information only in the current content: there is no separate side-gap exit, so do not expect a second entrance command to work. The knife is the authored alternate solution to the thorn screen. The adventure does not prescribe a saving throw, passive check, custom roll, or consumable-item use, so this walkthrough does not invent one.

## Coverage of the implemented mechanics

| Mechanic | Where this route shows it |
|---|---|
| Player question and answer | Mira's conversation, or any choice the DM presents |
| Player ability check | Steps 6, 8 and 12 use authored Wisdom or Dexterity checks |
| Fixture interaction | Steps 9 and 12 |
| Take, drop and give | Steps 2–4 and 13 |
| Scene and adventure exits | Steps 5, 7, 10 and 14 |
| Initiative, attacks, damage, AC and HP | Step 11 when combat begins |
| Hidden DM rolls and monster actions | Watchers and defenders in steps 8–11 |
| Rule lookup and campaign memory | Optional: ask the DM to explain an SRD combat rule or recall what Mira told Rosalind |
| Saving throw, passive check and custom roll | Implemented, but not authored by this adventure |
| Content reads (`get_scene`, `get_object`, `get_campaign`) | Internal DM operations; they are not player actions |
