You are given the full situation (`evidence`, including authored fixture
checks and secrets) and the player's move (`request.payload`). Decide
whether the move calls for an uncertain check at all, and if so, its DC.

Answer with:
- `applies`: `true` when this move needs a check or save before it
  succeeds or fails; `false` when the fiction already settles it.
- `dc`: the difficulty class, or `null` when `applies` is `false`. Prefer
  an authored DC already present in `evidence` (a fixture's own check or a
  secret's own DC) over inventing one.
- `dc_source`: `"authored"` when `dc` came from `evidence` itself,
  `"rules"` when you set it from general 5e SRD guidance instead, `null`
  when `applies` is `false`.
- `consequence_ids`: ids from `evidence`'s own `consequences` that this
  move's failure should trigger, if any.

Never decide the roll itself -- only whether one is needed and at what DC.
