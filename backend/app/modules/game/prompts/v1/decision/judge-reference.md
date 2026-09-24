The player's move names something ambiguously (a name that fits more than
one actor, item, fixture or exit in `evidence`, or nothing you can pin
down at all). Decide which one, if any, they meant.

Answer with:
- `chosen_id`: the single id from `evidence` you are confident they meant,
  or `null` when you cannot tell.
- `ask_choice`: when `chosen_id` is `null`, the ids of the candidates the
  player should be asked to pick between; empty when `chosen_id` is set.

Never invent an id that is not in `evidence`.
