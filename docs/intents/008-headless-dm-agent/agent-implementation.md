- Persisting turns (record_action, record_narration) needs a turn id minted per turn, so the turn-id plumbing comes first. DmContext.turn_id already exists; record_action becomes its writer.
- Every interrupt-based step (ask_player, request_player_roll) needs the Postgres checkpointer, otherwise a paused graph dies with the process.
- Checkpointer thread is per active play session. Long-term memory (campaign, adventure, scene state, creature/object positions, event log recap) is hydrated from the database on session bootstrap (`load_context`).
- validate_state should come before any tool that can refuse (attack, take, use_exit), so a refusal never crashes a turn.
- lookup_rule is blocked on the SRD module gaining a search function. Skip it until then.
- Content read tools depend on nothing and can go anywhere.

Ordered list

1. [x] record_action and record_narration nodes: the turn writes player_action and narration events with usage. From here every turn leaves a trace in the timeline.
2. [x] Postgres checkpointer replacing InMemorySaver for session-level persistence. Delete demo_graph.py here.
3. [x] validate_state node: mechanic errors become tool results the model narrates around.
4. [x] Content read tools: get_scene, get_object, get_campaign.
5. [x] Roll tools without a player click: resolve_check, resolve_save, passive_check, roll_initiative.
6. [x] load_context node: scene, character, awaiting state, creature/object state, and recap injected into the prompt on a cold/resumed thread.
7. [x] ask_player as an interrupt node, plus request_player_roll resuming through resolve_roll_request.
8. [x] Action tools: interact, take, drop, give, use_item, use_exit.
9. [x] Combat tools: attack, damage.
10. [x] ~~Progression tools: enter_adventure, activate_campaign_run~~ (Out of scope for DM agent: lifecycle transitions and adventure entry are triggered via API/UI).
11. [x] Memory tool recall.
12. [x] guard node. Last, because it needs the full set of tools and state to know what counts as out-of-band.
13. [x] lookup_rule, once SRD search exists.

Working around the missing UI

Yes, easily. Only two actions need the player mid-turn: answering a question and clicking a requested roll. Both become a LangGraph interrupt, and resuming is Command(resume=...) on the active session thread. In the CLI `app game play`, the interactive loop stays on the session thread across turns to resume seamlessly. For rolls, the CLI or API client can resolve the roll request before resuming the graph. The graph never learns whether the CLI or a browser answered, so nothing has to change when the UI arrives except adding a route that invokes the agent turn with the session thread.