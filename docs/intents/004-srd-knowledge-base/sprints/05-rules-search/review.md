---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: –
---
# Review: Sprint 05 — a rules question comes back with passages we can cite

## What changed
A rules question can now be asked from the command line and answered from the ingested SRD: the best-matching passages come back first, each with the chapter path that cites it, its position within the section, and a distance score. The rulebook was re-imported so that each passage is indexed together with its heading trail, which is what makes a spell findable by its name. The search function is the one the future DM tool will call.

## How to check it
- Ask "how does half cover work": the first passage is Combat › Cover, with the three degrees of cover.
- Ask "what happens when a creature is frightened": the first passage is the Frightened condition.
- Ask "what does fire bolt do" with a limit of three: the first passage is the Fire Bolt spell, and only three passages come back.
- Without a limit, five passages come back.
- Against an empty rulebook the command stops with the same empty-corpus message the status command uses, before contacting the model gateway.

## Heads-up
- No relevance floor yet: weaker look-alikes such as Half-Dragon still appear below the right answer. The next sprint pins the floor. The score shown is a distance, lower is closer, so that floor will be a maximum.
- Some chapter paths read oddly, for example Fire Bolt appears under Acid Arrow. The passage is the right one; the nesting comes from how the source's headings are split and is proposed as a backlog item.
- Re-importing cost about one cent.

Brief: docs/intents/004-srd-knowledge-base/sprints/05-rules-search/brief.md

## Verdict
