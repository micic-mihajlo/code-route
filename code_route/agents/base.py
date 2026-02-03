"""Base agent class and types for the multi-agent system."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from ..providers.base import BaseProvider
    from ..tools.base import BaseTool
    from ..core.events import EventBus


class AgentRole(str, Enum):
    """Roles that agents can fulfill."""
    ORCHESTRATOR = "orchestrator"
    CODER = "coder"
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    PLANNER = "planner"


@dataclass
class AgentCapabilities:
    """Describes what an agent can do."""
    can_write_code: bool = False
    can_read_files: bool = False
    can_execute_commands: bool = False
    can_search_web: bool = False
    can_delegate: bool = False
    can_review: bool = False
    tool_names: Set[str] = field(default_factory=set)


@dataclass
class AgentTask:
    """A task for an agent to execute."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    parent_task_id: Optional[str] = None
    preferred_agent: Optional[AgentRole] = None
    priority: int = 0  # Higher = more important
    max_iterations: int = 10

    @classmethod
    def create(cls, description: str, **context) -> "AgentTask":
        """Create a new task with description and optional context."""
        return cls(description=description, context=context)


@dataclass
class AgentResult:
    """Result from agent task execution."""
    task_id: str
    success: bool
    output: Any
    error: Optional[str] = None
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    subtask_results: List["AgentResult"] = field(default_factory=list)
    iterations_used: int = 0
    tokens_used: int = 0

    @classmethod
    def ok(cls, task_id: str, output: Any, artifacts: Optional[List[Dict]] = None) -> "AgentResult":
        """Create a successful result."""
        return cls(task_id=task_id, success=True, output=output, artifacts=artifacts or [])

    @classmethod
    def err(cls, task_id: str, error: str) -> "AgentResult":
        """Create an error result."""
        return cls(task_id=task_id, success=False, output="", error=error)


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    Agents are autonomous units that can:
    - Execute tasks using their assigned tools
    - Delegate work to other agents (if capable)
    - Communicate via the event bus
    - Maintain conversation context

    Each agent has a specific role and set of capabilities.
    """

    def __init__(
        self,
        provider: "BaseProvider",
        tools: List["BaseTool"],
        event_bus: Optional["EventBus"] = None,
    ):
        self.provider = provider
        self.tools = {tool.name: tool for tool in tools}
        self.event_bus = event_bus
        self._conversation_history: List[Dict[str, Any]] = []

    @property
    @abstractmethod
    def role(self) -> AgentRole:
        """The role this agent fulfills."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> AgentCapabilities:
        """What this agent can do."""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """
        System prompt defining the agent's behavior.

        Should include:
        - Role description
        - Available capabilities
        - Guidelines for task execution
        - Response format expectations
        """
        pass

    @property
    def available_tools(self) -> List[str]:
        """Names of tools available to this agent."""
        return list(self.tools.keys())

    @abstractmethod
    async def execute(self, task: AgentTask) -> AgentResult:
        """
        Execute a task.

        Args:
            task: The task to execute

        Returns:
            AgentResult with outcome and any artifacts
        """
        pass

    async def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event if event bus is configured."""
        if self.event_bus:
            from ..core.events import Event, EventType
            event = Event(
                type=EventType(event_type),
                data=data,
                source=f"agent:{self.role.value}"
            )
            await self.event_bus.publish_nowait(event)

    def _get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get OpenAI-format tool schemas for all available tools."""
        return [tool.to_schema() for tool in self.tools.values()]

    def _build_messages(self, task: AgentTask) -> List[Dict[str, Any]]:
        """Build message list for LLM call."""
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]

        # Add any conversation history
        messages.extend(self._conversation_history)

        # Add the task
        task_content = f"Task: {task.description}"
        if task.context:
            task_content += f"\n\nContext:\n{self._format_context(task.context)}"

        messages.append({"role": "user", "content": task_content})

        return messages

    def _to_provider_messages(self, messages: List[Dict[str, Any]]) -> List["Message"]:
        """
        Convert internal dict message history to strongly typed Message objects.

        Preserves tool-call metadata so multi-step tool loops remain valid.
        """
        from ..core.types import Message, MessageRole, ToolCall

        converted: List[Message] = []

        for msg in messages:
            role = MessageRole(msg["role"])
            content = msg.get("content", "")
            if content is None:
                content = ""

            parsed_tool_calls: Optional[List[ToolCall]] = None
            raw_tool_calls = msg.get("tool_calls")
            if raw_tool_calls:
                parsed_tool_calls = []
                for raw_tc in raw_tool_calls:
                    if isinstance(raw_tc, ToolCall):
                        parsed_tool_calls.append(raw_tc)
                        continue

                    if not isinstance(raw_tc, dict):
                        continue

                    # Accept both {"name","arguments"} and OpenAI-style {"function": {...}}.
                    if "function" in raw_tc and isinstance(raw_tc["function"], dict):
                        name = raw_tc["function"].get("name")
                        arguments = raw_tc["function"].get("arguments", {})
                    else:
                        name = raw_tc.get("name")
                        arguments = raw_tc.get("arguments", {})

                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {}

                    if not isinstance(arguments, dict) or not name:
                        continue

                    parsed_tool_calls.append(
                        ToolCall(
                            id=raw_tc.get("id", ""),
                            name=name,
                            arguments=arguments,
                        )
                    )

            converted.append(
                Message(
                    role=role,
                    content=content,
                    tool_calls=parsed_tool_calls or None,
                    tool_call_id=msg.get("tool_call_id"),
                    name=msg.get("name"),
                )
            )

        return converted

    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context dict for inclusion in prompt."""
        parts = []
        for key, value in context.items():
            if isinstance(value, str) and len(value) > 500:
                value = value[:500] + "..."
            parts.append(f"- {key}: {value}")
        return "\n".join(parts)

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._conversation_history.clear()


class DelegatingAgent(BaseAgent):
    """
    Agent that can delegate tasks to other agents.

    Used as base for the Orchestrator and any agent that needs
    to coordinate with other agents.
    """

    def __init__(
        self,
        provider: "BaseProvider",
        tools: List["BaseTool"],
        event_bus: Optional["EventBus"] = None,
        agent_registry: Optional["AgentRegistry"] = None,
    ):
        super().__init__(provider, tools, event_bus)
        self.agent_registry = agent_registry

    async def delegate(self, task: AgentTask, target_role: AgentRole) -> AgentResult:
        """
        Delegate a task to another agent.

        Args:
            task: The task to delegate
            target_role: The role of the agent to delegate to

        Returns:
            Result from the delegated agent
        """
        if not self.agent_registry:
            return AgentResult.err(task.id, "No agent registry configured")

        agent = self.agent_registry.get(target_role)
        if not agent:
            return AgentResult.err(task.id, f"No agent found for role: {target_role}")

        # Emit delegation event
        await self._emit_event("agent.delegated", {
            "from": self.role.value,
            "to": target_role.value,
            "task_id": task.id,
        })

        return await agent.execute(task)
