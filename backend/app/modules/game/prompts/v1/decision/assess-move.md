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
- `secret_index`: when `dc_source` is `"authored"` and the check is a
  hidden fact, the index of the matching entry in `evidence.secrets`
  (`0` for the first, `1` for the second, ...). `null` otherwise.
- `fixture_id` and `check_action`: when `dc_source` is `"authored"` and
  the check is a fixture's own, the fixture's own `id` and the matching
  check's own `action`. `null` otherwise.
- `consequence_ids`: ids from `evidence`'s own `consequences` that this
  move's failure should trigger, if any.

Never decide the roll itself -- only whether one is needed and at what DC.
Never invent a `secret_index`, `fixture_id` or `check_action` that is not
in `evidence`; when `dc_source` is `"authored"` you must name exactly one
of a `secret_index` or a `fixture_id`/`check_action` pair.
