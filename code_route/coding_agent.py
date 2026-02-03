"""Single-agent coding loop with tool orchestration and optional JSON events."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional

from .core.types import Message, MessageRole, ToolCall, ToolSchema, Usage
from .providers.base import BaseProvider
from .tools.base import BaseTool, ToolResult


EventSink = Callable[[Dict[str, Any]], Optional[Awaitable[None]]]


@dataclass
class AgentRunResult:
    """Result of one coding-agent run."""

    content: str
    usage: Usage = field(default_factory=Usage)
    iterations: int = 0
    tool_calls: int = 0


class CodingAgent:
    """
    Pi-style single coding-agent loop:
    - ask model
    - execute tool calls
    - continue until final answer or iteration cap
    """

    def __init__(
        self,
        provider: BaseProvider,
        tools: Iterable[BaseTool],
        *,
        max_iterations: int = 10,
        event_sink: Optional[EventSink] = None,
    ):
        self.provider = provider
        self.tools = {tool.name: tool for tool in tools}
        self.max_iterations = max_iterations
        self._event_sink = event_sink
        self._tool_schemas = [
            ToolSchema(
                name=tool.name,
                description=tool.description,
                parameters=tool.input_schema,
            )
            for tool in self.tools.values()
        ]

    async def _emit(self, event_type: str, **payload: Any) -> None:
        if not self._event_sink:
            return
        event = {
            "type": event_type,
            "timestamp": time.time(),
            "payload": payload,
        }
        result = self._event_sink(event)
        if inspect.isawaitable(result):
            await result

    async def _execute_tool(self, call: ToolCall) -> ToolResult:
        tool = self.tools.get(call.name)
        if not tool:
            return ToolResult.err(f"Unknown tool: {call.name}")

        arguments = call.arguments
        if arguments is None:
            parsed_arguments: Dict[str, Any] = {}
        elif isinstance(arguments, dict):
            parsed_arguments = arguments
        elif isinstance(arguments, str):
            try:
                decoded = json.loads(arguments)
            except json.JSONDecodeError:
                return ToolResult.err(
                    f"Invalid tool arguments for {call.name}: expected object JSON"
                )
            if not isinstance(decoded, dict):
                return ToolResult.err(
                    f"Invalid tool arguments for {call.name}: expected JSON object"
                )
            parsed_arguments = decoded
        else:
            return ToolResult.err(
                f"Invalid tool arguments for {call.name}: unsupported type "
                f"{type(arguments).__name__}"
            )

        try:
            return await tool.execute_async(**parsed_arguments)
        except TypeError as exc:
            return ToolResult.err(f"Invalid arguments for {call.name}: {exc}")

    async def run(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 4096,
    ) -> AgentRunResult:
        usage = Usage()
        tool_call_count = 0
        working_messages = list(messages)

        for iteration in range(1, self.max_iterations + 1):
            await self._emit("assistant.iteration.started", iteration=iteration)
            response = await self.provider.complete(
                working_messages,
                tools=self._tool_schemas or None,
                max_tokens=max_tokens,
            )

            usage += response.usage
            await self._emit(
                "assistant.iteration.completed",
                iteration=iteration,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                has_tool_calls=bool(response.tool_calls),
            )

            if response.tool_calls:
                tool_call_count += len(response.tool_calls)
                working_messages.append(
                    Message(
                        role=MessageRole.ASSISTANT,
                        content=response.content or "",
                        tool_calls=response.tool_calls,
                    )
                )

                for tc in response.tool_calls:
                    await self._emit(
                        "tool.call.started",
                        name=tc.name,
                        id=tc.id,
                        arguments=tc.arguments,
                    )
                    started_at = time.time()
                    result = await self._execute_tool(tc)
                    elapsed_ms = int((time.time() - started_at) * 1000)
                    await self._emit(
                        "tool.call.completed",
                        name=tc.name,
                        id=tc.id,
                        success=result.success,
                        error=result.error,
                        output_preview=(result.output[:400] + "...")
                        if len(result.output) > 400
                        else result.output,
                        elapsed_ms=elapsed_ms,
                    )

                    tool_text = result.output if result.success else f"Error: {result.error}"
                    working_messages.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=tool_text,
                            tool_call_id=tc.id,
                            name=tc.name,
                        )
                    )
                continue

            await self._emit("assistant.completed", content=response.content)
            return AgentRunResult(
                content=response.content or "",
                usage=usage,
                iterations=iteration,
                tool_calls=tool_call_count,
            )

        await self._emit("assistant.failed", reason="max_iterations_reached")
        return AgentRunResult(
            content="Error: Reached maximum tool iterations.",
            usage=usage,
            iterations=self.max_iterations,
            tool_calls=tool_call_count,
        )


def make_json_event_sink() -> EventSink:
    """Create a sink that prints one JSON event per line."""

    def sink(event: Dict[str, Any]) -> None:
        print(json.dumps(event, ensure_ascii=True))

    return sink
