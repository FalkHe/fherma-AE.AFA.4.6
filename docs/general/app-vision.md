# App vision

What the AI Dungeon Master is, who it is for, and what a player experiences.
No implementation here: the shape of the system is
[architecture.md](architecture.md), the data model is [model.md](model.md),
the game terms are [glossary.md](glossary.md), and the course requirements are
[requirement-map.md](requirement-map.md).

## Purpose

A single-player Dungeons & Dragons (5e SRD) game run entirely by an AI agent.
The agent narrates, interprets free-form player actions, rolls dice, looks up
rules and keeps game state consistent across play sessions.

**Target users:** people who want to try pen & paper without a group and
without learning the rules first. The player types what their character does
in plain words; nobody has to own a rulebook, find four friends or agree on a
date.

## Core principles

- **The player never has to know the rules.** Every rule the game needs, the
  agent looks up and applies. Terms are explained where they appear, not
  assumed.
- **The dice are real.** Outcomes come from actual rolls against actual target
  numbers, and the player can see every roll that was not deliberately hidden.
  The agent narrates results; it does not decide them.
- **The world remembers.** One save spans a whole campaign. Anything the agent
  invents becomes fact and stays fact — the NPC named in adventure 1 is the
  same NPC in adventure 3.
- **The story is not on rails.** Scenes are written as facts, intentions and
  consequences rather than as scripts, so the agent improvises within a stated
  truth instead of reciting a branch.
- **Some things stay hidden.** Secrets are resolved without leaking them: the
  player sees a filtered view, and the fact that a roll happened is not a tell.
- **The player UI is not a control panel.** Model choice, temperature, system
  prompt and DM personality live in a separate developer drawer; the player
  experience holds none of it.

## The player experience

1. **Make a character in plain words.** The player describes an idea — "shy,
   strong, small, clever" — answers a follow-up question or two, and gets a
   finished character sheet with a portrait. No stat allocation, no class
   glossary.
2. **Play by saying what you do.** Free-form input each turn. The agent
   narrates, asks when it needs a decision, and resolves anything uncertain
   with a roll.
3. **See the state that matters.** Hit points, armour class, inventory and
   turn order beside the narration, so the player never has to track anything
   on paper.
4. **Trust it by watching it work.** A filtered trace shows the visible rolls,
   the rules the agent cited and what each turn cost in tokens.
5. **Come back later.** A playthrough list resumes exactly where play stopped,
   including everything the agent invented in between.

## Scope

Single player, one campaign at a time, text plus portraits. Multiplayer, maps
and voice are out of scope and belong to a later capstone; the only concession
the design makes to them is described in [model.md](model.md).
