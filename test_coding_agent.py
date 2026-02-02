"""Focused tests for the single-loop coding agent behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest

from code_route.coding_agent import CodingAgent
from code_route.core.types import CompletionResponse, Message, MessageRole, ToolCall, ToolSchema, Usage
from code_route.memory.session import SessionConfig, SessionManager
from code_route.providers.base import BaseProvider, ProviderCapabilities, ProviderConfig
from code_route.tools.base import BaseTool, ToolResult


class FakeProvider(BaseProvider):
    """Provider stub that returns pre-seeded responses."""

    def __init__(self, responses: list[CompletionResponse]):
        super().__init__(ProviderConfig(model="fake"))
        self._responses = list(responses)
        self.calls: list[list[Message]] = []

    @property
    def name(self) -> str:
        return "fake"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    async def complete(
        self,
        messages: list[Message],
        tools: Optional[list[ToolSchema]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[list[str]] = None,
    ) -> CompletionResponse:
        _ = (tools, temperature, max_tokens, stop)
        self.calls.append(list(messages))
        if not self._responses:
            raise RuntimeError("No fake responses left")
        return self._responses.pop(0)

    async def stream(
        self,
        messages: list[Message],
        tools: Optional[list[ToolSchema]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[list[str]] = None,
    ):
        _ = (messages, tools, temperature, max_tokens, stop)
        if False:
            yield ""  # pragma: no cover


class EchoTool(BaseTool):
    """Simple tool used for loop tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "echotool"

    @property
    def description(self) -> str:
        return "Echoes the input text"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        self.calls.append(kwargs)
        return ToolResult.ok(f"echo:{kwargs.get('text', '')}")


@pytest.mark.asyncio
async def test_coding_agent_runs_tool_loop() -> None:
    tool = EchoTool()
    provider = FakeProvider(
        responses=[
            CompletionResponse(
                content="I will call a tool",
                tool_calls=[
                    ToolCall(id="call-1", name="echotool", arguments={"text": "hello"}),
                ],
                usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            ),
            CompletionResponse(
                content="Done",
                usage=Usage(prompt_tokens=7, completion_tokens=3, total_tokens=10),
            ),
        ]
    )
    agent = CodingAgent(provider=provider, tools=[tool], max_iterations=4)

    result = await agent.run(
        [
            Message(role=MessageRole.SYSTEM, content="You are helpful."),
            Message(role=MessageRole.USER, content="Say hello"),
        ]
    )

    assert result.content == "Done"
    assert result.iterations == 2
    assert result.tool_calls == 1
    assert result.usage.total_tokens == 25
    assert tool.calls == [{"text": "hello"}]

    # Provider gets called twice and the second pass includes tool output.
    assert len(provider.calls) == 2
    last_message = provider.calls[1][-1]
    assert last_message.role == MessageRole.TOOL
    assert last_message.content == "echo:hello"


@pytest.mark.asyncio
async def test_coding_agent_parses_json_string_tool_arguments() -> None:
    tool = EchoTool()
    provider = FakeProvider(
        responses=[
            CompletionResponse(
                content="Calling tool",
                tool_calls=[
                    ToolCall(
                        id="call-2",
                        name="echotool",
                        arguments='{"text": "string-json"}',
                    ),
                ],
            ),
            CompletionResponse(content="All good"),
        ]
    )
    agent = CodingAgent(provider=provider, tools=[tool], max_iterations=4)

    result = await agent.run(
        [Message(role=MessageRole.USER, content="Use a string arg")]
    )

    assert result.content == "All good"
    assert tool.calls == [{"text": "string-json"}]


@pytest.mark.asyncio
async def test_coding_agent_handles_invalid_tool_arguments_gracefully() -> None:
    tool = EchoTool()
    provider = FakeProvider(
        responses=[
            CompletionResponse(
                content="Calling tool",
                tool_calls=[
                    ToolCall(
                        id="call-3",
                        name="echotool",
                        arguments="not-json",
                    ),
                ],
            ),
            CompletionResponse(content="Recovered"),
        ]
    )
    agent = CodingAgent(provider=provider, tools=[tool], max_iterations=4)

    result = await agent.run(
        [Message(role=MessageRole.USER, content="Use invalid args")]
    )

    assert result.content == "Recovered"
    assert tool.calls == []
    assert len(provider.calls) == 2
    tool_result_message = provider.calls[1][-1]
    assert tool_result_message.role == MessageRole.TOOL
    assert "Invalid tool arguments" in str(tool_result_message.content)


@pytest.mark.asyncio
async def test_branch_session_copies_parent_history(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)

    manager = SessionManager(
        SessionConfig(
            db_path=tmp_path / "memory.db",
            enable_rag=False,
        )
    )

    parent_id = await manager.start(project_path=str(project_dir), force_new=True)
    await manager.add_user_message("question")
    await manager.add_assistant_message("answer")

    child_id = await manager.branch_session(title="child")

    assert child_id != parent_id
    assert [msg.content for msg in manager.get_messages()] == ["question", "answer"]

    child = await manager.memory.get_conversation(child_id)
    assert child is not None
    assert child.parent_id == parent_id

    child_messages = await manager.memory.get_recent_messages(child_id, limit=10)
    assert [msg.content for msg in child_messages] == ["question", "answer"]

    tree = await manager.get_session_tree(project_path=str(project_dir))
    assert len(tree) == 1
    assert tree[0]["id"] == parent_id
    assert tree[0]["children"][0]["id"] == child_id
