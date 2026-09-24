"""Shared test fakes for the decisions/narration flow (sprint 011-06).

`ScriptedChatModel` stands in for a `BaseChatModel` built by
`model_call.build_model()`: it never calls a provider. `.ainvoke()` (and
`.invoke()`) pop the next scripted item in order; `bind_tools()` is a
no-op that returns `self` so a caller can still build a tool loop against
it; `with_structured_output(schema, include_raw=True)` returns a thin
wrapper whose own `.ainvoke()`/`.invoke()` pop the next scripted item and
parse it into `schema` - either the item already *is* a `schema` instance
(a decision under test scripted the parsed value directly) or it is an
`AIMessage` whose `.content` is JSON matching `schema`.
"""

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel


class _StructuredScriptedModel:
    """Returned by `ScriptedChatModel.with_structured_output()`."""

    def __init__(self, parent: "ScriptedChatModel", schema: type[BaseModel], include_raw: bool):
        self._parent = parent
        self._schema = schema
        self._include_raw = include_raw

    def _parse(self, item: Any) -> tuple[BaseModel, AIMessage]:
        if isinstance(item, self._schema):
            raw = AIMessage(content=item.model_dump_json())
            return item, raw
        if isinstance(item, AIMessage):
            content = item.content if isinstance(item.content, str) else json.dumps(item.content)
            return self._schema.model_validate_json(content), item
        raise TypeError(f"unscripted item for structured output: {item!r}")

    async def ainvoke(self, messages: object, *args: Any, **kwargs: Any) -> Any:
        item = self._parent._pop()
        parsed, raw = self._parse(item)
        if self._include_raw:
            return {"raw": raw, "parsed": parsed, "parsing_error": None}
        return parsed

    def invoke(self, messages: object, *args: Any, **kwargs: Any) -> Any:
        item = self._parent._pop()
        parsed, raw = self._parse(item)
        if self._include_raw:
            return {"raw": raw, "parsed": parsed, "parsing_error": None}
        return parsed


class ScriptedChatModel(BaseChatModel):
    """A `BaseChatModel` that replays a fixed script instead of calling a
    provider.

    `script` is consumed in order across `.ainvoke()`/`.invoke()` and any
    `with_structured_output()` wrapper's calls alike - one shared cursor,
    matching one model making a sequence of calls. An entry that is a
    `BaseException` is raised instead of returned.
    """

    script: list[Any] = []

    def __init__(self, script: Sequence[Any], **kwargs: Any) -> None:
        super().__init__(script=list(script), **kwargs)
        # Plain attribute, not a pydantic field: `BaseChatModel` is a
        # pydantic model and forbids unset extra fields, so this is set
        # after `super().__init__()` rather than declared as a class
        # attribute. Counts `bind_tools()` calls so a test can assert a
        # narration call never bound tools, without changing the no-op
        # return every other scripted test already relies on.
        object.__setattr__(self, "bind_tools_calls", 0)

    def _pop(self) -> Any:
        if not self.script:
            raise AssertionError("ScriptedChatModel: no more scripted items")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        object.__setattr__(self, "bind_tools_calls", self.bind_tools_calls + 1)
        return self

    def with_structured_output(
        self, schema: type[BaseModel], *, include_raw: bool = False, **kwargs: Any
    ) -> _StructuredScriptedModel:
        return _StructuredScriptedModel(self, schema, include_raw)

    async def ainvoke(self, messages: object, *args: Any, **kwargs: Any) -> AIMessage:
        item = self._pop()
        return item if isinstance(item, AIMessage) else AIMessage(content=str(item))

    def invoke(self, messages: object, *args: Any, **kwargs: Any) -> AIMessage:
        item = self._pop()
        return item if isinstance(item, AIMessage) else AIMessage(content=str(item))

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        item = self._pop()
        message = item if isinstance(item, AIMessage) else AIMessage(content=str(item))
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "scripted-chat-model"
