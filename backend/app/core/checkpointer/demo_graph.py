"""THROWAWAY FIXTURE - sprint 07's acceptance-check graph, not product
surface. It exists only so `app checkpoint demo start` / `demo resume`
(`commands.py`) can demonstrate AC2/AC3: a graph that interrupts in one CLI
process and resumes, from Postgres, in a separate one. Phase 7 deletes this
module and replaces it with the real character-creation graph -- nothing
here should be extended, imported by product code, or used as a template
for anything beyond this sprint's demo.

Two nodes, one interrupt:

- `"one"` reads `seed` off the graph's own input (already durable in the
  checkpoint before this node's task ever runs, unlike anything computed
  fresh inside the node - see below) and calls `interrupt(seed)`. The first
  invocation raises out of `interrupt()`, pausing the graph; the second
  (`Command(resume=...)`) returns the resume payload and lets the node
  finish, writing both `left` (the interrupted-at value) and the resume
  payload to state.
- `"two"` combines them into `answer`.

Any code a node runs *before* its `interrupt()` call re-executes in full
when that node is resumed (verified live: a value computed fresh there
came out different on each of two separate `.invoke()` calls on the same
thread). Reading `seed` out of `state` - set once, at graph input, before
`"one"` ever starts - sidesteps that: it is unaffected by the re-run and
is genuinely the value `start()`'s caller supplied, unchanged, which is
what lets `resume()`'s answer prove the state crossed the process boundary
rather than being recomputed by the second process.
"""

import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt


class DemoState(TypedDict, total=False):
    seed: str
    left: str
    resumed: str
    answer: str


def _produce_and_interrupt(state: DemoState) -> dict:
    value = state["seed"]
    resumed = interrupt(value)
    return {"left": value, "resumed": resumed}


def _combine(state: DemoState) -> dict:
    return {"answer": f"{state['left']}|{state['resumed']}"}


def _build(checkpointer) -> CompiledStateGraph:
    graph = StateGraph(DemoState)
    graph.add_node("one", _produce_and_interrupt)
    graph.add_node("two", _combine)
    graph.add_edge(START, "one")
    graph.add_edge("one", "two")
    graph.add_edge("two", END)
    return graph.compile(checkpointer=checkpointer)


async def start(checkpointer, thread_id: str) -> object:
    """Run the demo graph forward, on `thread_id`, until it interrupts.
    Seeds the run with a fresh value each call, so the value handed back
    here - and later echoed inside `resume()`'s answer - differs run to
    run. Returns the interrupt's value; raises if the graph unexpectedly
    ran to completion without pausing."""
    graph = _build(checkpointer)
    config = {"configurable": {"thread_id": thread_id}}
    seed = f"seed-{uuid.uuid4()}"
    result = await graph.ainvoke({"seed": seed}, config=config)
    interrupts = result.get("__interrupt__")
    if not interrupts:
        raise RuntimeError("the demo graph ran to completion without interrupting")
    return interrupts[0].value


async def resume(checkpointer, thread_id: str, value: str) -> str:
    """Resume, on `thread_id`, a run previously paused by `start()`,
    supplying `value` as the interrupt's resume payload. Returns the
    combined `<left>|<value>` answer; raises a readable error - not the
    bare `KeyError` node `"one"` would otherwise raise reading `state["seed"]`
    off an empty state - if `thread_id` was never started, and raises if the
    graph did not reach `"two"`."""
    config = {"configurable": {"thread_id": thread_id}}
    existing = await checkpointer.aget_tuple(config)
    if existing is None:
        raise RuntimeError(f"thread {thread_id!r} has no interrupted state to resume")
    graph = _build(checkpointer)
    result = await graph.ainvoke(Command(resume=value), config=config)
    answer = result.get("answer")
    if answer is None:
        raise RuntimeError("the demo graph did not produce an answer on resume")
    return answer
