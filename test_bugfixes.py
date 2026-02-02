"""Regression tests for protocol, sandboxing, and event-schema fixes."""

from __future__ import annotations

import io
import json

import pytest

from code_route.cli.app import AppConfig, CodeRouteApp
from code_route.cli.panels import ToolStatus
from code_route.coding_agent import CodingAgent
from code_route.core.events import Event, EventBus, EventType
from code_route.core.types import CompletionResponse, Message, ToolSchema
from code_route.mcp.handlers import ResourceHandler
from code_route.mcp.server import MCPServer
from code_route.providers.base import BaseProvider, ProviderCapabilities, ProviderConfig


class NoopProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "noop"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> CompletionResponse:
        _ = (messages, tools, temperature, max_tokens, stop)
        return CompletionResponse(content="")

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ):
        _ = (messages, tools, temperature, max_tokens, stop)
        if False:
            yield ""  # pragma: no cover


def test_mcp_send_message_uses_utf8_byte_length() -> None:
    server = MCPServer()
    output = io.BytesIO()
    server._stdout = output

    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"text": "ć"},
    }
    server._send_message(message)

    raw = output.getvalue()
    header, payload = raw.split(b"\r\n\r\n", 1)
    content_length = None
    for line in header.split(b"\r\n"):
        if line.startswith(b"Content-Length:"):
            content_length = int(line.split(b":", 1)[1].strip())
            break

    assert content_length is not None
    assert content_length == len(payload)
    assert json.loads(payload.decode("utf-8"))["result"]["text"] == "ć"


@pytest.mark.asyncio
async def test_mcp_read_message_handles_utf8_framing() -> None:
    server = MCPServer()
    message = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "ping",
        "params": {"emoji": "🧠"},
    }
    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    framed = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload
    server._stdin = io.BytesIO(framed)

    parsed = await server._read_message()
    assert parsed == message


@pytest.mark.asyncio
async def test_resource_handler_blocks_prefix_path_escape(tmp_path) -> None:
    base_path = tmp_path / "project"
    base_path.mkdir()

    outside_path = tmp_path / "project_evil"
    outside_path.mkdir()
    secret = outside_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")

    inside = base_path / "inside.txt"
    inside.write_text("ok", encoding="utf-8")

    handler = ResourceHandler(base_path=base_path)

    denied = await handler.read_resource(f"file:///{secret.as_posix()}")
    denied_text = denied["contents"][0]["text"]
    assert "Access denied" in denied_text

    allowed = await handler.read_resource(f"file:///{inside.as_posix()}")
    assert allowed["contents"][0]["text"] == "ok"


@pytest.mark.asyncio
async def test_cli_event_handlers_accept_agent_payload_aliases() -> None:
    bus = EventBus()
    app = CodeRouteApp(config=AppConfig(), event_bus=bus)
    await app._setup_event_handlers()

    await bus.publish(
        Event(
            type=EventType.TOOL_STARTED,
            data={"tool": "greptool", "args": {"pattern": "foo"}},
        )
    )
    assert len(app.tool_list.executions) == 1
    tool_exec = app.tool_list.executions[0]
    assert tool_exec.name == "greptool"
    assert tool_exec.status == ToolStatus.RUNNING

    await bus.publish(
        Event(
            type=EventType.TOOL_COMPLETED,
            data={"tool": "greptool", "success": True},
        )
    )
    tool_exec = app.tool_list.executions[0]
    assert tool_exec.status == ToolStatus.SUCCESS
    assert tool_exec.output_summary == "success"

    await bus.publish(
        Event(
            type=EventType.TOOL_COMPLETED,
            data={"tool": "greptool", "success": False, "error": "boom"},
        )
    )
    tool_exec = app.tool_list.executions[0]
    assert tool_exec.status == ToolStatus.ERROR
    assert tool_exec.error == "boom"

    await bus.publish(
        Event(
            type=EventType.AGENT_STARTED,
            data={"agent": "orchestrator", "description": "Inspect repository"},
        )
    )
    assert app.agent_panel.root is not None
    assert app.agent_panel.root.name == "orchestrator"
    assert app.agent_panel.root.status == "working"
    assert app.agent_panel.root.task == "Inspect repository"

    await bus.publish(
        Event(
            type=EventType.AGENT_COMPLETED,
            data={"agent": "orchestrator"},
        )
    )
    assert app.agent_panel.root.status == "complete"


@pytest.mark.asyncio
async def test_coding_agent_event_sink_awaits_generic_awaitable() -> None:
    await_called = {"value": False}

    class ProbeAwaitable:
        def __await__(self):
            await_called["value"] = True
            if False:
                yield None
            return None

    def sink(_event):
        return ProbeAwaitable()

    agent = CodingAgent(
        provider=NoopProvider(ProviderConfig(model="noop")),
        tools=[],
        event_sink=sink,
    )
    await agent._emit("probe")
    assert await_called["value"] is True
