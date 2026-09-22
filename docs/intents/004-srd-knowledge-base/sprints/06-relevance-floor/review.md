---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/47
---
# Review: Sprint 06 — "no relevant rule" is an answer, not an empty guess

## What changed
A rules question the SRD does not cover now gets a clean "no relevant rule" instead of the nearest unrelated passage. The cut-off was measured today against the loaded rulebook: six in-corpus questions all scored well inside it, five off-topic questions all fell well outside it, with clear daylight between the two groups. In-corpus questions still answer exactly as before.

## How to check it
- Ask "how do I reload a plasma rifle": the answer is "no relevant rule" and the command exits normally.
- Ask "how does half cover work": Combat › Cover still comes first with the three degrees of cover.
- Ask anything off topic, for example the capital of France or pizza toppings: "no relevant rule".
- Against an empty rulebook the command still stops with the empty-corpus message and a failure exit, so the two cases cannot be confused.
- The module documentation records the cut-off and the eleven questions used to pick it.

## Heads-up
- The cut-off is a fixed constant tied to the current embedding model. A model change requires re-measuring it; the documentation says so.
- Lexical look-alikes that scored below the right answer in the previous sprint, such as Half-Dragon for a cover question, now mostly fall outside the cut-off, but a borderline one can still appear as a lower-ranked match.

Brief: docs/intents/004-srd-knowledge-base/sprints/06-relevance-floor/brief.md

## Verdict
Round 1: Approve. A question the rulebook does not cover — a plasma rifle, sourdough bread, a Kubernetes setting — now answers "no relevant rule" and ends normally, while "how does half cover work" still opens with the cover rule and its three degrees. An empty rulebook remains a clearly different, failing outcome, and the module documentation records the cut-off together with the eleven questions measured to pick it.
