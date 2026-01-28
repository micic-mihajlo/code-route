"""Coder agent specialized for code generation and modification."""

import asyncio
from typing import List, Optional, TYPE_CHECKING

from ..core.types import Message, MessageRole, ToolSchema
from .base import AgentCapabilities, AgentResult, AgentRole, AgentTask, BaseAgent

if TYPE_CHECKING:
    from ..providers.base import BaseProvider
    from ..tools.base import BaseTool
    from ..core.events import EventBus


CODER_PROMPT = '''You are a Coder agent specialized in writing, editing, and refactoring code.

## Your Capabilities
- Create new files and directories
- Edit existing code precisely
- Run bash commands for testing and building
- Use linting tools for code quality
- Search codebase with grep and glob

## Coding Standards
1. **Follow existing patterns** - Match the style and conventions of the codebase
2. **Minimal changes** - Only modify what's necessary to complete the task
3. **No over-engineering** - Keep solutions simple and focused
4. **Test your changes** - Run linters and tests when appropriate

## Response Format
1. First, briefly explain your approach (1-2 sentences)
2. Make the necessary code changes using tools
3. Verify changes with linting if applicable
4. Summarize what was done

## Important Rules
- Read files before editing them
- Use precise edits (Edit tool) instead of full file rewrites when possible
- Don't add comments or documentation unless requested
- Don't refactor code that doesn't need to change
- If unsure about conventions, check similar files first
'''


class CoderAgent(BaseAgent):
    """
    Agent specialized for code generation, modification, and refactoring.

    Has access to:
    - File creation and editing tools
    - Bash for running commands
    - Linting tools
    - Code search (grep, glob)
    """

    @property
    def role(self) -> AgentRole:
        return AgentRole.CODER

    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_write_code=True,
            can_read_files=True,
            can_execute_commands=True,
            can_search_web=False,
            can_delegate=False,
            can_review=False,
            tool_names=set(self.tools.keys()),
        )

    @property
    def system_prompt(self) -> str:
        return CODER_PROMPT

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a coding task."""
        await self._emit_event("agent.started", {
            "agent": self.role.value,
            "task_id": task.id,
            "description": task.description,
        })

        iterations = 0
        total_tokens = 0
        artifacts = []

        try:
            messages = self._build_messages(task)

            while iterations < task.max_iterations:
                iterations += 1

                # Get LLM response
                tool_schemas = [
                    ToolSchema(
                        name=t.name,
                        description=t.description,
                        parameters=t.input_schema
                    )
                    for t in self.tools.values()
                ]

                response = await self.provider.complete(
                    messages=[Message(role=MessageRole(m["role"]), content=m["content"]) for m in messages],
                    tools=tool_schemas,
                )

                total_tokens += response.usage.total_tokens

                # Process tool calls if any
                if response.tool_calls:
                    tool_results = []

                    for tc in response.tool_calls:
                        tool = self.tools.get(tc.name)
                        if not tool:
                            tool_results.append(f"Error: Tool '{tc.name}' not found")
                            continue

                        await self._emit_event("tool.started", {
                            "tool": tc.name,
                            "args": tc.arguments,
                        })

                        result = await tool.execute_async(**tc.arguments)

                        # Track file artifacts
                        if tc.name in ["filecreatortool", "fileedittool", "multiedittool"]:
                            file_path = tc.arguments.get("file_path") or tc.arguments.get("path")
                            if file_path:
                                artifacts.append({
                                    "type": "file_modified",
                                    "path": file_path,
                                    "operation": tc.name,
                                })

                        await self._emit_event("tool.completed", {
                            "tool": tc.name,
                            "success": result.success,
                        })

                        tool_results.append(result.output if result.success else f"Error: {result.error}")

                    # Add to conversation
                    messages.append({
                        "role": "assistant",
                        "content": response.content,
                        "tool_calls": [
                            {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                            for tc in response.tool_calls
                        ]
                    })

                    for tc, result in zip(response.tool_calls, tool_results):
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        })

                    continue

                # No tool calls - final response
                await self._emit_event("agent.completed", {
                    "agent": self.role.value,
                    "task_id": task.id,
                    "success": True,
                })

                return AgentResult(
                    task_id=task.id,
                    success=True,
                    output=response.content,
                    artifacts=artifacts,
                    iterations_used=iterations,
                    tokens_used=total_tokens,
                )

            return AgentResult(
                task_id=task.id,
                success=False,
                output="",
                error=f"Reached maximum iterations ({task.max_iterations})",
                artifacts=artifacts,
                iterations_used=iterations,
                tokens_used=total_tokens,
            )

        except Exception as e:
            await self._emit_event("agent.error", {
                "agent": self.role.value,
                "task_id": task.id,
                "error": str(e),
            })
            return AgentResult.err(task.id, str(e))
