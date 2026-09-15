"""Shared fake for the sprint-01 LLM acceptance tests: a stand-in for
`langchain_openrouter.ChatOpenRouter`, monkeypatched onto
`app.core.llm.service.ChatOpenRouter` per the sprint's binding interface I1
("`ChatOpenRouter` is a module-level name — monkeypatch `service.ChatOpenRouter`
to capture kwargs without a key").

`test_service.py` (AC3) and `test_commands.py` (AC2, AC4, AC5) both drive the
real `chat_model(...)` / `app llm chat` code paths and fake out only this one
network-touching class, so the fake needs to look like a LangChain chat model
*class*: callers construct it, then call `.invoke(prompt)` or
`.stream(prompt)` on the instance.

Deliberately holds no import of `app.core.llm` at module scope: that package
does not exist yet (this sprint is building it), and a conftest-level import
failure would take every test under `tests/core/` down with it, not just the
llm ones. The two test modules import it themselves and are expected to fail
collection until the seam lands — that is the correct red state.
"""

import pytest


@pytest.fixture
def recording_chat_open_router():
    """A fresh fake `ChatOpenRouter` class per test. `.calls` records every
    constructor call's kwargs; `.response` / `.chunks` script what
    `.invoke()` / `.stream()` hand back."""

    class _RecordingChatOpenRouter:
        calls: list[dict] = []
        response = None
        chunks: list = []

        def __init__(self, *args, **kwargs):
            type(self).calls.append(kwargs)

        def invoke(self, prompt):
            return type(self).response

        def stream(self, prompt):
            yield from type(self).chunks

    return _RecordingChatOpenRouter
