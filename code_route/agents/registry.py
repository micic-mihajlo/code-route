"""Agent registry for managing and discovering agents."""

from typing import Dict, List, Optional, Type, TYPE_CHECKING

from .base import AgentRole, BaseAgent

if TYPE_CHECKING:
    from ..providers.base import BaseProvider
    from ..tools.base import BaseTool
    from ..core.events import EventBus


class AgentRegistry:
    """
    Registry for managing agent instances.

    The registry handles:
    - Agent registration and discovery
    - Agent instantiation with shared resources
    - Agent lifecycle management
    """

    def __init__(
        self,
        provider: "BaseProvider",
        tools: List["BaseTool"],
        event_bus: Optional["EventBus"] = None,
    ):
        self.provider = provider
        self.all_tools = {tool.name: tool for tool in tools}
        self.event_bus = event_bus
        self._agents: Dict[AgentRole, BaseAgent] = {}
        self._agent_classes: Dict[AgentRole, Type[BaseAgent]] = {}

    def register_class(self, role: AgentRole, agent_class: Type[BaseAgent]) -> None:
        """Register an agent class for a role."""
        self._agent_classes[role] = agent_class

    def register(self, agent: BaseAgent) -> None:
        """Register an instantiated agent."""
        self._agents[agent.role] = agent

    def get(self, role: AgentRole) -> Optional[BaseAgent]:
        """
        Get an agent by role.

        If agent is not instantiated, creates it from registered class.
        """
        if role in self._agents:
            return self._agents[role]

        if role in self._agent_classes:
            agent = self._create_agent(role)
            self._agents[role] = agent
            return agent

        return None

    def get_all(self) -> List[BaseAgent]:
        """Get all registered agents."""
        # Ensure all registered classes are instantiated
        for role in self._agent_classes:
            if role not in self._agents:
                self._agents[role] = self._create_agent(role)

        return list(self._agents.values())

    def _create_agent(self, role: AgentRole) -> BaseAgent:
        """Create an agent instance from its registered class."""
        agent_class = self._agent_classes[role]

        # Determine which tools this agent should have
        agent_tools = self._get_tools_for_role(role)

        # Check if agent class accepts agent_registry (for delegating agents)
        import inspect
        sig = inspect.signature(agent_class.__init__)
        params = list(sig.parameters.keys())

        if "agent_registry" in params:
            return agent_class(
                provider=self.provider,
                tools=agent_tools,
                event_bus=self.event_bus,
                agent_registry=self,
            )
        else:
            return agent_class(
                provider=self.provider,
                tools=agent_tools,
                event_bus=self.event_bus,
            )

    def _get_tools_for_role(self, role: AgentRole) -> List["BaseTool"]:
        """Get the tools appropriate for an agent role."""
        # Tool assignments by role
        role_tools: Dict[AgentRole, List[str]] = {
            AgentRole.ORCHESTRATOR: list(self.all_tools.keys()),  # All tools
            AgentRole.CODER: [
                "filecreatortool", "fileedittool", "filecontentreadertool",
                "bashtool", "lintingtool", "diffeditortool", "multiedittool",
                "createfolderstool", "lstool", "globtool", "greptool",
            ],
            AgentRole.RESEARCHER: [
                "webscrapertool", "duckduckgotool", "filecontentreadertool",
                "greptool", "globtool", "lstool", "browsertool",
            ],
            AgentRole.REVIEWER: [
                "filecontentreadertool", "greptool", "globtool", "lstool",
                "lintingtool", "bashtool", "diffeditortool",
            ],
            AgentRole.PLANNER: [
                "filecontentreadertool", "greptool", "globtool", "lstool",
                "agenttool", "todowritetool",
            ],
        }

        tool_names = role_tools.get(role, [])
        return [
            self.all_tools[name]
            for name in tool_names
            if name in self.all_tools
        ]

    def has_role(self, role: AgentRole) -> bool:
        """Check if an agent is registered for a role."""
        return role in self._agents or role in self._agent_classes

    def list_roles(self) -> List[AgentRole]:
        """List all registered roles."""
        roles = set(self._agents.keys()) | set(self._agent_classes.keys())
        return list(roles)


def create_default_registry(
    provider: "BaseProvider",
    tools: List["BaseTool"],
    event_bus: Optional["EventBus"] = None,
) -> AgentRegistry:
    """
    Create a registry with all default agents registered.

    Args:
        provider: LLM provider for agents
        tools: All available tools
        event_bus: Optional event bus for communication

    Returns:
        Configured AgentRegistry
    """
    from .orchestrator import OrchestratorAgent
    from .coder import CoderAgent
    from .researcher import ResearcherAgent
    from .reviewer import ReviewerAgent
    from .planner import PlannerAgent

    registry = AgentRegistry(provider, tools, event_bus)

    # Register agent classes
    registry.register_class(AgentRole.ORCHESTRATOR, OrchestratorAgent)
    registry.register_class(AgentRole.CODER, CoderAgent)
    registry.register_class(AgentRole.RESEARCHER, ResearcherAgent)
    registry.register_class(AgentRole.REVIEWER, ReviewerAgent)
    registry.register_class(AgentRole.PLANNER, PlannerAgent)

    return registry
