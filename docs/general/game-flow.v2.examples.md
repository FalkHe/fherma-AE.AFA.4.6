# Game Flow v2 Examples

These scenarios check that the five-node game flow covers common play. They are
behavior examples, not a requirement for one end-to-end test per scenario. The
minimal test suite may combine several scenarios.

## Reading the flows

The graph has five nodes:

- **advance** selects the next required effect;
- **decide** makes one structured model decision;
- **execute** performs one deterministic operation;
- **await_player** interrupts for a roll or meaningful choice;
- **narrate** writes prose from allowed evidence.

Every worker returns to **advance**. The abbreviated mechanic lists below omit
that return edge when it is obvious.

Durable positions and stats live in objects. Active requests, action plans and
combat order live in the LangGraph checkpoint. Events retain player actions,
rolls, mechanic outcomes and narration after transient state is cleared.

## 1. Opening a run

No player input.

Expected:

- Enter the first adventure and position the hero if this has not happened.
- Load the initial scene and its visible occupants and objects.
- Resolve any authored passive observation without asking the player to roll.
- Narrate only visible scene facts and passively discovered facts.
- Open the composer for the first player action.

### Mechanic

~~~text
advance
→ execute(enter adventure, when required)
→ execute(passive check, when authored)
→ narrate(opening from public evidence)
→ execute(record beat)
→ END
~~~

## 2. Talk to an NPC

Player input: “I talk to Mira.”

Expected:

- Resolve Mira from creatures present in the hero's scene.
- Use scene truth, Mira's intent and relevant recent history.
- Narrate Mira's response without inventing a roll or changing world state.
- If several Miras are valid candidates, use scenario 8 instead.

### Mechanic

~~~text
advance
→ decide(read move: talk; candidate: Mira)
→ decide(world or NPC response)
→ narrate(answer beat)
→ execute(record beat)
→ execute(complete action)
→ execute(close turn)
→ END
~~~

## 3. Active investigation

Player input: “I search the back of the cave for tracks.”

Expected:

- Match the action to an authored hidden fact when one applies.
- Choose Investigation or Perception from the authored check and action, not
  Deception.
- Freeze ability, skill, DC provenance, actor and consumer before requesting a
  roll.
- Interrupt for the player's Roll action.
- Sample the die only after resume and resolve it deterministically.
- Reveal the hidden fact only on success. On failure, narrate the unsuccessful
  search without claiming that no secret exists.

### Mechanic

~~~text
advance
→ decide(read and assess active search)
→ execute(request roll into checkpoint state)
→ await_player(Roll)
→ execute(roll player)
→ execute(resolve check)
→ narrate(outcome from the check event)
→ execute(record beat)
→ execute(complete action)
→ execute(close turn)
→ END
~~~

The same request, action and turn must resume after a normal process restart.
No pending-request table is involved.

## 4. Passive observation

Player input: “I look around while walking.”

Expected:

- Use a passive score only when the authored fact permits passive discovery.
- Do not interrupt and do not sample a die.
- Reveal a fact only when the passive score meets its DC.
- Keep hidden facts out of narration on failure.

### Mechanic

~~~text
advance
→ decide(read and assess look)
→ execute(passive check)
→ narrate(visible and discovered evidence)
→ execute(record beat)
→ execute(complete action)
→ execute(close turn)
→ END
~~~

## 5. Move to another scene

Player input: “I follow the cart track to the treeline.”

Expected:

- Resolve the phrase to one exit from the current scene.
- Assess its authored condition from established facts.
- If allowed, update the hero's position before narrating arrival.
- Reload the destination situation and retire old-scene combat obligations.
- If blocked, leave position unchanged and narrate the supported reason.
- If the exit completes the adventure, enter its successor or finish the run.

### Mechanic

~~~text
advance
→ decide(read move and assess exit condition)
→ execute(use exit)
→ execute(enter next adventure, when required)
→ narrate(arrival, blocked, or completion beat)
→ execute(record beat)
→ execute(complete action)
→ execute(close turn)
→ END
~~~

## 6. Handle an item

Player input: “I take the bent horseshoe.”

Expected:

- Resolve an item reachable in the current scene.
- Validate that it is movable and the hero can carry it.
- Update ownership before narrating the result.
- Use the same operation family for drop and give, with receiver validation.
- If item use has no authored mechanic, narrate a supported refusal instead of
  inventing a permanent effect.

### Mechanic

~~~text
advance
→ decide(read move and bind reachable item)
→ execute(take, drop, or give)
→ narrate(outcome from item_moved or refusal)
→ execute(record beat)
→ execute(complete action)
→ execute(close turn)
→ END
~~~

## 7. Work a fixture and trigger a consequence

Player input: “When the watchers look away, I lift the lashed brush aside.”

Expected:

- Resolve the authored fixture action, its DC and any carried bypass item.
- Use the bypass without a roll when its authored condition applies.
- Otherwise interrupt for the player's roll and consume it through the fixture
  interaction.
- Persist the opened way on success.
- On a noisy failure, assess the authored consequence. If it makes nearby
  creatures hostile, admit combat without granting the hero another action.

### Mechanic

~~~text
advance
→ decide(assess fixture and bypass)
→ execute(request roll, unless bypassed)
→ await_player(Roll, unless bypassed)
→ execute(roll player, unless bypassed)
→ execute(interact)
→ decide(world reaction and consequence)
→ execute(set hostility, when triggered)
→ when combat starts: advance(combat scheduling; continue with scenario 11)
→ otherwise: narrate(fixture outcome)
→ otherwise: execute(record beat)
→ otherwise: execute(complete action)
→ otherwise: execute(close turn)
→ END
~~~

## 8. Resolve an ambiguous reference

Player input: “I attack one of the goblins.”

Expected:

- Resolve all living, present goblins as candidates.
- Let **decide** select one only when fiction makes them interchangeable or a
  prior target makes the intent clear.
- Otherwise present meaningful named choices and interrupt.
- Store the private choice-key-to-object mapping in graph state.
- Resume the same action and turn with the selected target.
- If the target moved, died or became invalid while waiting, reject the stale
  binding and resolve candidates again.

### Mechanic

~~~text
advance
→ decide(read move and judge candidates)
→ execute(request choice into checkpoint state)
→ await_player(named choices)
→ execute(accept choice)
→ decide(validate the resumed attack plan)
→ continue with scenario 11
~~~

## 9. Ask a rules question

Player input: “Can I shove a goblin off a ledge?”

Expected:

- Recognize a rules question before treating it as a declared attack.
- Retrieve only SRD rules through rules RAG.
- Interpret the retrieved passages for the current situation.
- Narrate the answer and citations without mutating state or admitting a combat
  round for a pure question.
- If the player also clearly declares the shove, continue into the supported
  mechanic after explaining the rule.

### Mechanic

~~~text
advance
→ decide(read move: rules evidence required)
→ execute(lookup rule)
→ decide(interpret evidence)
→ narrate(rules answer)
→ execute(record beat)
→ execute(close turn)
→ END
~~~

## 10. Recall older play

Player input: “What did Mira promise me at the farm?”

Expected:

- Detect that the answer is outside the bounded recent transcript.
- Retrieve semantically matching narration.
- Include surrounding player-visible events from each matched turn so the
  original player wording and answer are available.
- Answer only from recalled evidence.
- Do not copy the complete transcript into graph state.

### Mechanic

~~~text
advance
→ decide(read move: older history required)
→ execute(recall history)
→ decide(interpret recalled evidence)
→ narrate(answer beat)
→ execute(record beat)
→ execute(close turn)
→ END
~~~

## 11. Start or continue combat

Player input: “I attack Grettle with the shepherd's knife.”

Expected:

- Validate that Grettle is alive and present and that the hero carries the
  named weapon.
- Establish the project's simplified side initiative once when combat starts:
  request one hero-side roll and roll once for the hostile side automatically.
- The higher side acts first for the whole fight; do not reroll initiative each
  round. The hero side wins a tie. Use a stable order for creatures within the
  hostile side.
- When the hero acts, narrate the attempt, interrupt for the attack roll and
  resolve hit, miss or critical hit.
- A hit must interrupt for damage and apply it before another actor or turn
  closure. A miss must not request damage.
- Each eligible hostile receives at most one action in the admitted round.
  Monster attack and damage rolls are automatic and never interrupt.
- Skip creatures that are dead, absent or no longer hostile when their turn
  arrives.
- End with a closing beat. If combat continues, retain the combat cursor across
  the next player turn. The next player message admits a round and resets the
  actor index.

### Mechanic

~~~text
advance
→ decide(read attack and bind target and weapon)
→ execute(request initiative, when combat is new)
→ await_player(Roll, when initiative is new)
→ execute(roll hero-side initiative)
→ execute(roll hostile-side initiative)
→ execute(settle initiative)
→ advance(schedule next eligible actor)

Hero action:
→ narrate(attempt beat)
→ execute(record beat)
→ execute(request attack roll)
→ await_player(Roll)
→ execute(roll player)
→ execute(resolve attack)
→ on hit: execute(request damage roll)
→ on hit: await_player(Roll)
→ on hit: execute(roll player damage)
→ on hit: execute(apply damage)

Monster action:
→ decide(monster action: attack, flee, surrender, parley, or hold)
→ on attack: execute(roll monster attack)
→ on attack: execute(resolve attack)
→ on hit: execute(roll monster damage)
→ on hit: execute(apply damage)

→ advance(schedule remaining eligible actors)
→ narrate(closing or ending beat)
→ execute(record beat)
→ execute(close turn)
→ END
~~~

Combat does not run unattended until someone dies. One player message admits
one round. After the eligible actors finish, the composer opens for the next
player action if the fight continues.

Side initiative is an intentional house simplification of SRD initiative. It
matches the existing playthrough service and avoids storing a separate
initiative result for every creature.

## 12. End combat

Cover these distinct endings:

### All hostiles are defeated or leave

- Recompute eligibility after every mutation.
- Clear the combat cursor when no active hostile remains.
- Narrate the aftermath and reopen normal exploration.

### A hostile flees, surrenders or parleys

- **decide** may choose only behavior supported by disposition and situation.
- Movement or hostility changes go through deterministic operations.
- A creature that left the scene cannot attack later in the round.
- Clear combat only when no active hostility remains.

### The hero is downed

- Apply damage and down state before any defeat narration.
- Preempt remaining actor actions and player requests.
- Finish the run with defeat and narrate an ending beat.
- Do not reopen the composer.

### Mechanic

~~~text
execute(apply damage or actor behavior)
→ advance(refresh eligibility and terminal state)
→ execute(clear combat or finish run)
→ narrate(aftermath or defeat)
→ execute(record beat)
→ END
~~~

## 13. Unsupported or stale action

Player input: “I unlock the iron door with the silver key.”

Assume there is no iron door or silver key in the current situation.

Expected:

- Bind no invented object IDs and perform no state mutation.
- Return a supported refusal based on the current scene.
- Do not admit a combat round for the unsupported declaration.
- Narrate what the hero can perceive and invite another action.

The same recovery applies when an exit, target or choice was valid when planned
but is stale before execution: refresh the situation, discard the invalid
binding and either resolve again or narrate the refusal.

### Mechanic

~~~text
advance
→ decide(read move)
→ execute(validate references; no valid candidate)
→ narrate(unsupported or stale beat)
→ execute(record beat)
→ execute(close turn)
→ END
~~~

## 14. Resolve a saving throw consequence

Player input: “I force open the trapped coffer.”

Assume opening it triggers an authored poison needle that allows a Dexterity
saving throw.

Expected:

- Resolve the initial fixture action before assessing its consequence.
- Freeze the save ability, DC, actor, source and consequence before requesting
  a roll.
- Interrupt for the hero's Roll action and route that roll only to the stored
  saving-throw consumer.
- Apply authored damage or another durable consequence after the save result.
- Do not count the forced save as a second voluntary hero action.
- Narrate only the resolved save and applied consequence.

### Mechanic

~~~text
advance
→ decide(read fixture action)
→ execute(interact)
→ decide(assess authored consequence)
→ execute(request saving-throw roll into checkpoint state)
→ await_player(Roll)
→ execute(roll player)
→ execute(resolve save)
→ execute(apply authored consequence, when required)
→ narrate(outcome beat)
→ execute(record beat)
→ execute(complete action)
→ execute(close turn)
→ END
~~~

## Coverage summary

Together these scenarios cover:

- opening and ordinary conversation;
- recent and long-term context;
- passive and active checks;
- saving throws caused by authored consequences;
- player rolls and choices across interrupts;
- movement, items, fixtures and consequences;
- SRD rules retrieval;
- reference validation and recovery;
- initiative, hero and monster actions, damage priority and multi-turn combat;
- victory, departure, surrender, parley and terminal defeat.

The implementation plan should still keep only representative end-to-end tests.
Most variations belong in deterministic service, scheduler or registry tests.
