# Game

The game module owns the LangGraph orchestration for a single-player D&D
turn. It interprets player input and writes narration, while deterministic
mechanics and all lasting state changes belong to `playthrough.service`.

## Flow

Every opening and player turn uses one graph:

```text
START -> advance -> decide       -> advance
                 -> execute      -> advance
                 -> await_player -> advance
                 -> narrate      -> advance
                 -> END
```

`advance` is the only scheduler and router. It reloads the authoritative
situation and chooses one typed effect from checkpoint state and current world
facts. The four workers perform one boundary operation and return to
`advance`. The graph has exactly five nodes and no worker-to-worker edges.

## Agent files

- `agent/flow_state.py` — checkpoint-native turn, move, action, combat,
  request, result, reaction, narration, usage and error types.
- `agent/effects.py` — the typed effects emitted by the scheduler.
- `agent/advance.py` — the pure priority scheduler and deterministic plan
  builders.
- `agent/decisions.py` — focused structured decision strategies. Decisions
  may bind only the read-only `lookup_rule` and `recall_history` aids, with a
  bounded call budget; every proposed operation and reference is validated.
- `agent/operations.py` and `agent/operations_world.py` — the single typed
  operation registry. Handlers call public playthrough services and return
  typed results; they do not own transactions.
- `agent/narration.py` — one unbound model call over public situation data and
  recorded evidence. It drafts text; `record_beat` persists it.
- `agent/flow_nodes.py` — the five node functions and their runtime context.
- `agent/graph.py` — graph composition and fresh-turn state construction.
- `service.py` — authentication/ownership boundary, checkpoint lifecycle and
  the HTTP/CLI turn entry point.

## Persistence rules

LangGraph checkpoints hold orchestration state: active requests, responses,
operation results, rolls, pending hits, combat order and narration progress.
The database holds durable world facts and the event stream used for transcript
display and bounded memory recall. Requests remain paired transcript events;
the checkpoint, rather than an event scan, decides what resumes next.

Expected mechanic failures are typed `refused` results. Ownership, identity,
lifecycle and infrastructure failures remain exceptions. Services own their
transaction boundaries, and the game module never edits ORM state directly.
