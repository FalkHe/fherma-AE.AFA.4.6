Given the full situation (`evidence`, including hidden npc intent and
secrets) and what just happened (`request.payload`), decide how the world
around the hero reacts right now -- nothing the hero themselves did.

Answer with:
- `reactions`: zero or more reactions, each an object with a
  `reaction_id` you make up for this answer, a `kind` naming one of the
  operation kinds you were told this decision may propose, and a
  `payload` built only from ids already present in `evidence`.

Never invent an id that is not in `evidence`. Never propose a reaction
kind outside the ones you were told are allowed.
