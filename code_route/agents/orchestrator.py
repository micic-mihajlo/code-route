"""Orchestrator agent that coordinates other agents."""

import asyncio
import json
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..core.types import Message, MessageRole, ToolCall
from .base import (
    AgentCapabilities,
    AgentResult,
    AgentRole,
    AgentTask,
    BaseAgent,
    DelegatingAgent,
)

if TYPE_CHECKING:
    from ..providers.base import BaseProvider
    from ..tools.base import BaseTool
    from ..core.events import EventBus
    from .registry import AgentRegistry


ORCHESTRATOR_PROMPT = '''You are an Orchestrator agent that coordinates complex tasks by delegating to specialized agents.

## Your Role
- Analyze user requests and break them into subtasks
- Delegate subtasks to the most appropriate specialized agent
- Synthesize results from multiple agents into coherent responses
- Handle failures gracefully with retries or alternative approaches

## Available Agents
1. **CODER** - Writes, edits, and refactors code. Use for implementation tasks.
2. **RESEARCHER** - Searches web and codebase. Use for information gathering.
3. **REVIEWER** - Reviews code, runs tests. Use for quality assurance.
4. **PLANNER** - Creates detailed plans. Use for complex task decomposition.

## Delegation Guidelines
- Simple code changes → CODER directly
- Need information first → RESEARCHER, then CODER
- Quality concerns → REVIEWER after CODER
- Complex/unclear tasks → PLANNER first

## Response Format
When delegating, use the delegate_task tool with:
- agent_role: One of "coder", "researcher", "reviewer", "planner"
- task_description: Clear, specific description of what to do
- context: Any relevant information the agent needs

## Important Rules
1. Always explain your delegation strategy briefly
2. For simple tasks, handle directly with available tools
3. For complex tasks, create a plan first
4. Synthesize agent results into a coherent response
5. If an agent fails, try an alternative approach
'''


class OrchestratorAgent(DelegatingAgent):
    """
    Main coordinator agent that manages task execution.

    The Orchestrator:
    1. Receives user requests
    2. Analyzes complexity and requirements
    3. Delegates to specialized agents
    4. Coordinates parallel execution when possible
    5. Synthesizes final responses
    """

    def __init__(
        self,
        provider: "BaseProvider",
        tools: List["BaseTool"],
        event_bus: Optional["EventBus"] = None,
        agent_registry: Optional["AgentRegistry"] = None,
    ):
        super().__init__(provider, tools, event_bus, agent_registry)
        self._active_tasks: Dict[str, AgentTask] = {}

    @property
    def role(self) -> AgentRole:
        return AgentRole.ORCHESTRATOR

    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_write_code=True,
            can_read_files=True,
            can_execute_commands=True,
            can_search_web=True,
            can_delegate=True,
            can_review=True,
            tool_names=set(self.tools.keys()),
        )

    @property
    def system_prompt(self) -> str:
        return ORCHESTRATOR_PROMPT

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a task, potentially delegating to other agents."""
        await self._emit_event("agent.started", {
            "agent": self.role.value,
            "task_id": task.id,
            "description": task.description,
        })

        self._active_tasks[task.id] = task
        iterations = 0
        total_tokens = 0

        try:
            # Build initial messages
            messages = self._build_messages(task)

            while iterations < task.max_iterations:
                iterations += 1

                # Get LLM response
                from ..core.types import ToolSchema
                tool_schemas = [
                    ToolSchema(
                        name=t.name,
                        description=t.description,
                        parameters=t.input_schema
                    )
                    for t in self.tools.values()
                ]

                # Add delegation tool
                delegate_tool = ToolSchema(
                    name="delegate_task",
                    description="Delegate a subtask to a specialized agent",
                    parameters={
                        "type": "object",
                        "properties": {
                            "agent_role": {
                                "type": "string",
                                "enum": ["coder", "researcher", "reviewer", "planner"],
                                "description": "The role of the agent to delegate to"
                            },
                            "task_description": {
                                "type": "string",
                                "description": "Clear description of the subtask"
                            },
                            "context": {
                                "type": "object",
                                "description": "Additional context for the agent"
                            }
                        },
                        "required": ["agent_role", "task_description"]
                    }
                )
                tool_schemas.append(delegate_tool)

                response = await self.provider.complete(
                    messages=self._to_provider_messages(messages),
                    tools=tool_schemas,
                )

                total_tokens += response.usage.total_tokens

                # Check if we have tool calls
                if response.tool_calls:
                    # Process tool calls
                    tool_results = await self._process_tool_calls(response.tool_calls, task)

                    # Add assistant message with tool calls
                    messages.append({
                        "role": "assistant",
                        "content": response.content,
                        "tool_calls": [
                            {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                            for tc in response.tool_calls
                        ]
                    })

                    # Add tool results
                    for tc, result in zip(response.tool_calls, tool_results):
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        })

                    continue

                # No tool calls - we have a final response
                await self._emit_event("agent.completed", {
                    "agent": self.role.value,
                    "task_id": task.id,
                    "success": True,
                })

                return AgentResult(
                    task_id=task.id,
                    success=True,
                    output=response.content,
                    iterations_used=iterations,
                    tokens_used=total_tokens,
                )

            # Hit iteration limit
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

        finally:
            del self._active_tasks[task.id]

    async def _process_tool_calls(
        self,
        tool_calls: List[ToolCall],
        parent_task: AgentTask
    ) -> List[str]:
        """Process tool calls, handling both regular tools and delegation."""
        results_by_id: Dict[str, str] = {}

        # Group independent tool calls for parallel execution
        delegation_calls = []
        regular_calls = []

        for tc in tool_calls:
            if tc.name == "delegate_task":
                delegation_calls.append(tc)
            else:
                regular_calls.append(tc)

        # Execute regular tools in parallel
        if regular_calls:
            regular_results = await asyncio.gather(*[
                self._execute_tool(tc)
                for tc in regular_calls
            ])
            for tc, result in zip(regular_calls, regular_results):
                results_by_id[tc.id] = result

        # Execute delegations (could be parallel too, but sequential is safer)
        for tc in delegation_calls:
            result = await self._handle_delegation(tc, parent_task)
            results_by_id[tc.id] = result

        # Return in the exact original tool-call order.
        return [results_by_id.get(tc.id, "Error: Missing tool result") for tc in tool_calls]

    async def _execute_tool(self, tool_call: ToolCall) -> str:
        """Execute a single tool call."""
        tool = self.tools.get(tool_call.name)
        if not tool:
            return f"Error: Tool '{tool_call.name}' not found"

        await self._emit_event("tool.started", {
            "tool": tool_call.name,
            "args": tool_call.arguments,
        })

        try:
            result = await tool.execute_async(**tool_call.arguments)

            await self._emit_event("tool.completed", {
                "tool": tool_call.name,
                "success": result.success,
            })

            return result.output if result.success else f"Error: {result.error}"

        except Exception as e:
            await self._emit_event("tool.error", {
                "tool": tool_call.name,
                "error": str(e),
            })
            return f"Error executing {tool_call.name}: {e}"

    async def _handle_delegation(
        self,
        tool_call: ToolCall,
        parent_task: AgentTask
    ) -> str:
        """Handle a delegation tool call."""
        args = tool_call.arguments
        role_str = args.get("agent_role", "").lower()
        description = args.get("task_description", "")
        context = args.get("context", {})

        # Map string to role
        role_map = {
            "coder": AgentRole.CODER,
            "researcher": AgentRole.RESEARCHER,
            "reviewer": AgentRole.REVIEWER,
            "planner": AgentRole.PLANNER,
        }

        role = role_map.get(role_str)
        if not role:
            return f"Error: Unknown agent role '{role_str}'"

        # Create subtask
        subtask = AgentTask(
            description=description,
            context=context,
            parent_task_id=parent_task.id,
            preferred_agent=role,
        )

        # Delegate
        result = await self.delegate(subtask, role)

        if result.success:
            return f"[{role_str.upper()} Agent Result]\n{result.output}"
        else:
            return f"[{role_str.upper()} Agent Error]\n{result.error}"

    async def chat(self, user_input: str) -> str:
        """
        Convenience method for simple chat interactions.

        Args:
            user_input: User message

        Returns:
            Assistant response
        """
        task = AgentTask.create(user_input)
        result = await self.execute(task)

        if result.success:
            return result.output
        else:
            return f"Error: {result.error}"
