---
title: "Sprint 4 Project Vision – AI Dungeon Master"
created: 2026-09-08
status: draft
tags:
  - sprint-04
  - project
  - vision
---

# AI Dungeon Master – Project Vision

## Purpose

A single-player Dungeons & Dragons (5e SRD) game run entirely by an AI agent. The agent narrates, interprets free-form player actions, rolls dice, looks up rules, and keeps all game state consistent across play sessions.

**Target users:** people who want to try pen & paper without a group or without learning the rules first.

**Guiding principle:** the project proves knowledge of AI agents (prompting, RAG, tools, memory, human-in-the-loop) – not game design. Keep everything else minimal.

## Decisions

- Single player only. Data model prepared for multi-user (user id on every record, `visibility` flag on state and rolls) – multiplayer is the capstone candidate.
- Content hierarchy: **Campaign** (series) > **Adventure** (one story, 3+ scenes) > **Scene** (one place/situation). A player's saved game is a **Playthrough** (never "session" – avoids collision with browser/HTTP sessions).
- Content, reasoning and mechanics are separate layers:
  - **Content** – campaigns, adventures, scenes and monster stats as structured JSON.
  - **Reasoning** – LLM agent decides how a scene plays out.
  - **Mechanics** – deterministic tools (dice, HP, state validation). The LLM never fakes a roll or edits state directly.
- Scenes are written as **facts + intentions + consequences**, not scripts. The agent improvises within the stated truth; anything it improvises is saved to the journal and treated as fact from then on.
- Hidden information uses passive checks (`10 + bonus` vs DC) or hidden rolls. The player-facing trace is filtered.
- Structured lookups (scenes, monsters) use JSON, not RAG. Only the SRD rules text is RAG.
- Stack: React web client, Python FastAPI backend, LangChain/LangGraph, OpenRouter.

## Components

### 1. Character Generation Agent (startup)

Player gives a rough idea and a few attributes in plain words ("shy, strong, small, clever"). The agent

- asks one or two follow-up questions if needed,
- derives race/class and ability scores from the description with a little randomness,
- generates a portrait (image API),
- writes the character sheet to state.

### 2. Adventure Content

- One campaign, one adventure, 3 scenes to start.
- AI-generated once, then hardcoded as JSON. A small CLI tool (`generate_adventure`) prompts the LLM with the SRD and enforces the schema, so output always matches the structure the game agent expects.
- Scene schema: `truth[]`, `npc_intent`, `consequences[]`, `hidden[] (check, dc, reveal)`, `monsters[]`, `exits{}`, optional `pressure`.

### 3. Rules Knowledge Base (RAG)

- D&D 5e SRD 5.1 (CC-BY-4.0), chunked into a vector store by a one-time ingest script.
- Agentic: the game agent decides whether a lookup is needed and may re-query.

### 4. Game Agent (LangGraph)

Loop: `narrate → decide (tool | ask_player) → tool → validate state → loop`, interrupt on `ask_player`.

Tools:

| Tool | Purpose |
|---|---|
| `roll_dice(expr, visibility)` | Deterministic dice; hidden rolls filtered from player view |
| `lookup_rule(query)` | RAG over SRD |
| `get_scene(id)` | Load scene facts |
| `get_monster(name)` | Stat block from JSON |
| `update_character(patch)` / `update_monster(id, patch)` | Validated state mutation |
| `start_combat()` / `end_round()` | Initiative and turn tracking |
| `add_journal_entry()` / `search_journal()` | Long-term memory |
| `ask_player(prompt, options)` | Human-in-the-loop interrupt |

Guard node before the agent: rejects prompt injection and out-of-band state changes ("my HP is 100").

### 5. Web Client

Narration pane · state panel (HP, AC, inventory, turn order) · filtered agent trace with roll log and rule citations · token/cost display · playthrough list · developer drawer (model, temperature, system prompt, DM personality) separated from the player UI.

## Requirement mapping

| Requirement | Covered by |
|---|---|
| Purpose & users | Solo AI DM for rule-free entry into PnP |
| ≥3 tools | 9 tools above |
| User interactions | `ask_player` every turn, character generation dialogue |
| UI | Web client above |
| Error handling | Invalid dice, unknown ids, state validation, LLM/tool timeouts, checkpoint resume |
| Documentation | README with glossary (DC/AC/HP), adventure authoring guide, tool reference, architecture decisions |

## Optional tasks targeted

| Task | Mechanic |
|---|---|
| Medium 1 – token usage & cost | Per turn / per playthrough in trace panel |
| Medium 2 – memory | Checkpointer (short-term), journal + canon inventions (long-term) |
| Medium 8 – security guard, dev/user split | Guard node, developer drawer |
| Hard 1 – agentic RAG | On-demand SRD lookup with re-query |
| Easy 2 – personality | DM tone switch |
| Easy 4 – model settings | Developer drawer |

Out of scope (future work / capstone): multiplayer, maps, voice.

## Glossary

- **d20** – 20-sided die. Every uncertain outcome is `d20 + bonus` vs a target number.
- **DC (Difficulty Class)** – target number for a check. Easy 10, medium 15, hard 20.
- **AC (Armor Class)** – target number an attacker must reach to hit you.
- **HP (Hit Points)** – health. 0 = down.
- **Passive check** – `10 + bonus` vs DC, no roll. Used for noticing hidden things without leaking information.
- **Initiative** – `d20 + Dexterity bonus` to determine turn order in combat.
- **SRD** – System Reference Document; the freely licensed subset of the D&D 5e rules.
- **Campaign / Adventure / Scene** – content hierarchy: series > story > place.
- **Playthrough** – one player's saved progress through an adventure.
