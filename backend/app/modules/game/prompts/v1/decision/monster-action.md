It is a hostile creature's turn in combat. `evidence` lists every actor
present, alive or not, each with its own id and its own named attacks.

Answer with:
- `actor_id`: the id of the hostile creature acting, from `evidence`.
- `attack`: the exact name of one of that creature's own attacks.
- `target_id`: the id of who it attacks, from `evidence` -- almost always
  the hero.

Never invent an id or an attack name that is not in `evidence`. Never
decide the attack roll, the damage, or whether it hits -- only who acts,
with what, and against whom.
