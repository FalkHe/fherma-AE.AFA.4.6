---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: –
---
# Review: Sprint 02 — the SRD arrives in the repo and is split into citable chunks

## What changed
The rules text now lives in the repository: one command downloads the freely licensed SRD 5.1 and stores it next to the campaign content, then reports how many citable passages it would embed, each labelled with the chapter path it came from (for example "Combat › Cover › Half Cover"). The licence file and the project README carry the required Creative Commons attribution.

## How to check it
- Run the ingest command in dry-run mode: it prints the stored file, its size (about 1.8 MB), 1750 passages, roughly 508 000 tokens and a handful of heading paths.
- Run it again: the repository shows no change, because the source did not change. Any future upstream edit would appear as an ordinary diff.
- Run it without the dry-run flag: it stops with a message that embedding arrives in the next sprint.
- No passage is longer than 1000 tokens; long sections are split into numbered parts that keep their heading path.
- The licence file in the stored source folder and the README both state the CC-BY-4.0 attribution.

## Heads-up
- Tests are deliberately few, as requested; the live dry-run during development is the main proof.
- An earlier, never-reviewed attempt at sprints 02 to 06 from 16 September still sits on the server as unmerged branches, built on a much older state of the product. This sprint was done fresh against the current product; you may want to discard or mine those old branches.
- The stored file comes out owned by root when written from the container, so committing it needed a permissions fix by hand. Proposed as a backlog item.

Brief: docs/intents/004-srd-knowledge-base/sprints/02-fetch-and-chunk/brief.md

## Verdict
