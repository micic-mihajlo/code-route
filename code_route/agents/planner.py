"""Planner agent specialized for task decomposition and planning."""

from typing import List, Optional, TYPE_CHECKING

from ..core.types import Message, MessageRole, ToolSchema
from .base import AgentCapabilities, AgentResult, AgentRole, AgentTask, BaseAgent

if TYPE_CHECKING:
    from ..providers.base import BaseProvider
    from ..tools.base import BaseTool
    from ..core.events import EventBus


PLANNER_PROMPT = '''You are a Planner agent specialized in task decomposition and implementation planning.

## Your Capabilities
- Analyze codebase structure
- Search for patterns and dependencies
- Read files to understand architecture
- Create structured task plans
- Manage todo lists for tracking

## Planning Guidelines
1. **Understand first** - Explore before planning
2. **Be specific** - Concrete steps, not vague goals
3. **Consider dependencies** - Order tasks correctly
4. **Identify risks** - Note potential blockers
5. **Keep it minimal** - Don't over-plan

## Plan Structure
1. **Goal**: What we're trying to achieve
2. **Context**: Relevant codebase information
3. **Approach**: High-level strategy
4. **Tasks**: Ordered list of specific steps
5. **Risks**: Potential issues and mitigations

## Response Format
```
## Goal
[One sentence describing the objective]

## Context
- [Relevant file/pattern discovered]
- [Existing conventions to follow]

## Approach
[2-3 sentences on strategy]

## Tasks
1. [ ] [Specific actionable task]
2. [ ] [Specific actionable task]
...

## Risks
- [Potential issue]: [Mitigation]
```

## Important Rules
- Explore the codebase before creating a plan
- Reference specific files and patterns found
- Keep tasks atomic and verifiable
- Don't plan more than necessary
'''


class PlannerAgent(BaseAgent):
    """
    Agent specialized for task decomposition and planning.

    Has access to:
    - File reading tools
    - Code search (grep, glob)
    - Directory listing
    - Todo management
    """

    @property
    def role(self) -> AgentRole:
        return AgentRole.PLANNER

    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_write_code=False,
            can_read_files=True,
            can_execute_commands=False,
            can_search_web=False,
            can_delegate=False,
            can_review=False,
            tool_names=set(self.tools.keys()),
        )

    @property
    def system_prompt(self) -> str:
        return PLANNER_PROMPT

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a planning task."""
        await self._emit_event("agent.started", {
            "agent": self.role.value,
            "task_id": task.id,
            "description": task.description,
        })

        iterations = 0
        total_tokens = 0
        explored_files = []

        try:
            messages = self._build_messages(task)

            while iterations < task.max_iterations:
                iterations += 1

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

                if response.tool_calls:
                    tool_results = []

                    for tc in response.tool_calls:
                        tool = self.tools.get(tc.name)
                        if not tool:
                            tool_results.append(f"Error: Tool '{tc.name}' not found")
                            continue

                        await self._emit_event("tool.started", {
                            "tool": tc.name,
                        })

                        result = await tool.execute_async(**tc.arguments)

                        # Track explored files
                        if tc.name in ["filecontentreadertool", "lstool"]:
                            path = tc.arguments.get("file_path") or tc.arguments.get("path", "")
                            if path:
                                explored_files.append(path)

                        await self._emit_event("tool.completed", {
                            "tool": tc.name,
                            "success": result.success,
                        })

                        tool_results.append(result.output if result.success else f"Error: {result.error}")

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

                await self._emit_event("agent.completed", {
                    "agent": self.role.value,
                    "task_id": task.id,
                    "success": True,
                })

                return AgentResult(
                    task_id=task.id,
                    success=True,
                    output=response.content,
                    artifacts=[{"type": "explored_files", "files": explored_files}] if explored_files else [],
                    iterations_used=iterations,
                    tokens_used=total_tokens,
                )

            return AgentResult(
                task_id=task.id,
                success=False,
                output="",
                error=f"Reached maximum iterations ({task.max_iterations})",
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
