"""
TUI panel components for Code Route CLI.

Provides reusable Rich components for:
- Tool execution display
- Agent hierarchy visualization
- Token usage tracking
- Status indicators
- Conversation display
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich.columns import Columns
from rich.align import Align
from rich.box import ROUNDED, HEAVY, SIMPLE
from rich.style import Style


class ToolStatus(Enum):
    """Status of a tool execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class ToolExecution:
    """Record of a tool execution."""
    name: str
    status: ToolStatus = ToolStatus.PENDING
    input_summary: str = ""
    output_summary: str = ""
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ToolPanel:
    """
    Display panel for tool executions.

    Shows tool name, status, inputs, and outputs
    with collapsible details.
    """

    STATUS_STYLES = {
        ToolStatus.PENDING: ("dim", "[...]"),
        ToolStatus.RUNNING: ("yellow", "[RUN]"),
        ToolStatus.SUCCESS: ("green", "[OK]"),
        ToolStatus.ERROR: ("red", "[ERR]"),
        ToolStatus.SKIPPED: ("dim", "[---]"),
    }

    def __init__(
        self,
        execution: ToolExecution,
        show_details: bool = True,
        compact: bool = False,
    ):
        self.execution = execution
        self.show_details = show_details
        self.compact = compact

    def render(self) -> Panel:
        """Render the tool panel."""
        style, icon = self.STATUS_STYLES[self.execution.status]

        # Header with tool name and status
        header = Text()
        header.append(f"{icon} ", style=style)
        header.append(self.execution.name, style="bold")

        if self.execution.duration_ms is not None:
            header.append(f" ({self.execution.duration_ms}ms)", style="dim")

        if self.compact:
            return Panel(header, border_style=style, box=SIMPLE)

        # Build content
        content_parts = [header]

        if self.show_details:
            if self.execution.input_summary:
                input_text = Text()
                input_text.append("Input: ", style="cyan")
                input_text.append(
                    self._truncate(self.execution.input_summary, 100),
                    style="dim"
                )
                content_parts.append(input_text)

            if self.execution.output_summary:
                output_text = Text()
                output_text.append("Output: ", style="green")
                output_text.append(
                    self._truncate(self.execution.output_summary, 100),
                    style="dim"
                )
                content_parts.append(output_text)

            if self.execution.error:
                error_text = Text()
                error_text.append("Error: ", style="red bold")
                error_text.append(self.execution.error, style="red")
                content_parts.append(error_text)

        return Panel(
            Group(*content_parts),
            border_style=style,
            box=ROUNDED,
            padding=(0, 1),
        )

    @staticmethod
    def _truncate(text: str, max_length: int) -> str:
        """Truncate text with ellipsis."""
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."


class ToolExecutionList:
    """
    Display a list of tool executions.

    Supports live updates during execution.
    """

    def __init__(self, title: str = "Tool Executions"):
        self.title = title
        self.executions: List[ToolExecution] = []

    def add(self, execution: ToolExecution) -> None:
        """Add an execution to the list."""
        self.executions.append(execution)

    def update(self, name: str, **kwargs) -> None:
        """Update an execution by name."""
        for exe in self.executions:
            if exe.name == name:
                for key, value in kwargs.items():
                    setattr(exe, key, value)
                break

    def render(self) -> Panel:
        """Render the execution list."""
        if not self.executions:
            return Panel(
                Text("No tools executed", style="dim"),
                title=self.title,
                border_style="dim",
            )

        table = Table(
            show_header=True,
            header_style="bold cyan",
            box=SIMPLE,
            padding=(0, 1),
        )
        table.add_column("Status", width=6)
        table.add_column("Tool", style="bold")
        table.add_column("Duration", width=10, justify="right")
        table.add_column("Result", style="dim")

        for exe in self.executions:
            style, icon = ToolPanel.STATUS_STYLES[exe.status]
            duration = f"{exe.duration_ms}ms" if exe.duration_ms else "-"
            result = exe.error or exe.output_summary[:50] if exe.output_summary else "-"

            table.add_row(
                Text(icon, style=style),
                exe.name,
                duration,
                ToolPanel._truncate(result, 40),
            )

        return Panel(
            table,
            title=f"[bold]{self.title}[/bold]",
            border_style="cyan",
        )


@dataclass
class AgentNode:
    """A node in the agent tree."""
    name: str
    role: str
    status: str = "idle"
    task: str = ""
    children: List["AgentNode"] = field(default_factory=list)


class AgentPanel:
    """
    Display panel for agent hierarchy.

    Shows tree structure of agents with their
    current status and tasks.
    """

    STATUS_ICONS = {
        "idle": "[dim]-[/dim]",
        "thinking": "[yellow]*[/yellow]",
        "working": "[cyan]>[/cyan]",
        "complete": "[green]+[/green]",
        "error": "[red]![/red]",
    }

    ROLE_COLORS = {
        "orchestrator": "bright_magenta",
        "coder": "bright_cyan",
        "researcher": "bright_green",
        "reviewer": "bright_yellow",
        "planner": "bright_blue",
    }

    def __init__(self, root: Optional[AgentNode] = None):
        self.root = root

    def set_root(self, root: AgentNode) -> None:
        """Set the root agent."""
        self.root = root

    def update_status(self, name: str, status: str, task: str = "") -> None:
        """Update an agent's status."""
        if self.root:
            self._update_recursive(self.root, name, status, task)

    def _update_recursive(
        self,
        node: AgentNode,
        name: str,
        status: str,
        task: str
    ) -> bool:
        """Recursively find and update agent."""
        if node.name == name:
            node.status = status
            if task:
                node.task = task
            return True

        for child in node.children:
            if self._update_recursive(child, name, status, task):
                return True
        return False

    def render(self) -> Panel:
        """Render the agent tree."""
        if not self.root:
            return Panel(
                Text("No agents active", style="dim"),
                title="Agents",
                border_style="dim",
            )

        tree = Tree(self._render_node(self.root))
        self._add_children(tree, self.root)

        return Panel(
            tree,
            title="[bold]Agent Hierarchy[/bold]",
            border_style="magenta",
        )

    def _render_node(self, node: AgentNode) -> Text:
        """Render a single node."""
        text = Text()

        # Status icon
        icon = self.STATUS_ICONS.get(node.status, "-")
        text.append(f"{icon} ")

        # Role with color
        color = self.ROLE_COLORS.get(node.role, "white")
        text.append(f"[{node.role}] ", style=f"{color} dim")

        # Name
        text.append(node.name, style="bold")

        # Task if present
        if node.task:
            text.append(f": {node.task}", style="dim")

        return text

    def _add_children(self, tree: Tree, node: AgentNode) -> None:
        """Recursively add children to tree."""
        for child in node.children:
            branch = tree.add(self._render_node(child))
            self._add_children(branch, child)


class TokenUsagePanel:
    """
    Display panel for token usage tracking.

    Shows input/output tokens, costs, and
    progress toward limits.
    """

    def __init__(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        max_tokens: Optional[int] = None,
        cost_per_1k_input: float = 0.0,
        cost_per_1k_output: float = 0.0,
    ):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.max_tokens = max_tokens
        self.cost_per_1k_input = cost_per_1k_input
        self.cost_per_1k_output = cost_per_1k_output

    def update(
        self,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
    ) -> None:
        """Update token counts."""
        if input_tokens is not None:
            self.input_tokens = input_tokens
        if output_tokens is not None:
            self.output_tokens = output_tokens

    def add(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Add to token counts."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    @property
    def total_tokens(self) -> int:
        """Get total token count."""
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost(self) -> float:
        """Calculate estimated cost in dollars."""
        input_cost = (self.input_tokens / 1000) * self.cost_per_1k_input
        output_cost = (self.output_tokens / 1000) * self.cost_per_1k_output
        return input_cost + output_cost

    def render(self, compact: bool = False) -> RenderableType:
        """Render the token usage display."""
        if compact:
            return self._render_compact()
        return self._render_full()

    def _render_compact(self) -> Text:
        """Render compact inline display."""
        text = Text()
        text.append("Tokens: ", style="dim")
        text.append(f"{self.input_tokens:,}", style="cyan")
        text.append(" in / ", style="dim")
        text.append(f"{self.output_tokens:,}", style="green")
        text.append(" out", style="dim")

        if self.estimated_cost > 0:
            text.append(f" (${self.estimated_cost:.4f})", style="yellow dim")

        return text

    def _render_full(self) -> Panel:
        """Render full panel display."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Label", style="dim")
        table.add_column("Value", justify="right")

        table.add_row("Input", Text(f"{self.input_tokens:,}", style="cyan"))
        table.add_row("Output", Text(f"{self.output_tokens:,}", style="green"))
        table.add_row(
            "Total",
            Text(f"{self.total_tokens:,}", style="bold white")
        )

        if self.estimated_cost > 0:
            table.add_row(
                "Est. Cost",
                Text(f"${self.estimated_cost:.4f}", style="yellow")
            )

        content = [table]

        # Progress bar if max is set
        if self.max_tokens:
            progress = Progress(
                TextColumn("[dim]Usage:[/dim]"),
                BarColumn(bar_width=20),
                TaskProgressColumn(),
            )
            task = progress.add_task("", total=self.max_tokens, completed=self.total_tokens)
            content.append(progress)

        return Panel(
            Group(*content),
            title="[bold]Token Usage[/bold]",
            border_style="yellow",
            padding=(0, 1),
        )


class StatusBar:
    """
    Bottom status bar for the CLI.

    Shows current model, status, and quick info.
    """

    def __init__(
        self,
        model: str = "",
        status: str = "Ready",
        provider: str = "",
    ):
        self.model = model
        self.status = status
        self.provider = provider
        self.extras: Dict[str, str] = {}

    def set_status(self, status: str) -> None:
        """Update status message."""
        self.status = status

    def set_extra(self, key: str, value: str) -> None:
        """Set extra info to display."""
        self.extras[key] = value

    def render(self) -> Panel:
        """Render the status bar."""
        parts = []

        # Model info
        if self.model:
            model_text = Text()
            model_text.append("Model: ", style="dim")
            model_text.append(self.model, style="cyan bold")
            if self.provider:
                model_text.append(f" ({self.provider})", style="dim")
            parts.append(model_text)

        # Status
        status_text = Text()
        status_text.append("Status: ", style="dim")

        status_style = "green" if self.status == "Ready" else "yellow"
        status_text.append(self.status, style=status_style)
        parts.append(status_text)

        # Extras
        for key, value in self.extras.items():
            extra_text = Text()
            extra_text.append(f"{key}: ", style="dim")
            extra_text.append(value, style="white")
            parts.append(extra_text)

        # Join with separator
        content = Text(" | ", style="dim").join(parts)

        return Panel(
            Align.center(content),
            style="dim",
            box=SIMPLE,
            padding=(0, 0),
        )


@dataclass
class Message:
    """A conversation message."""
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


class ConversationPanel:
    """
    Display panel for conversation history.

    Shows messages with role indicators
    and optional tool call details.
    """

    ROLE_STYLES = {
        "user": ("bright_blue", "You"),
        "assistant": ("bright_green", "Assistant"),
        "system": ("dim", "System"),
        "tool": ("yellow", "Tool"),
    }

    def __init__(self, max_messages: int = 50):
        self.messages: List[Message] = []
        self.max_messages = max_messages

    def add(self, role: str, content: str, **kwargs) -> None:
        """Add a message to the conversation."""
        self.messages.append(Message(role=role, content=content, **kwargs))

        # Trim if over limit
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

    def clear(self) -> None:
        """Clear conversation history."""
        self.messages = []

    def render(self, show_timestamps: bool = False) -> Panel:
        """Render the conversation."""
        if not self.messages:
            return Panel(
                Text("No messages yet", style="dim"),
                title="Conversation",
                border_style="dim",
            )

        parts = []
        for msg in self.messages:
            style, label = self.ROLE_STYLES.get(msg.role, ("white", msg.role))

            # Header
            header = Text()
            header.append(f"[{label}]", style=f"{style} bold")
            if show_timestamps:
                header.append(
                    f" {msg.timestamp.strftime('%H:%M:%S')}",
                    style="dim"
                )

            parts.append(header)

            # Content (truncated for display)
            content = msg.content
            if len(content) > 500:
                content = content[:497] + "..."

            content_text = Text(content, style=style)
            parts.append(content_text)
            parts.append(Text(""))  # Spacer

        return Panel(
            Group(*parts),
            title="[bold]Conversation[/bold]",
            border_style="blue",
            padding=(0, 1),
        )


class HelpPanel:
    """
    Display panel for keyboard shortcuts and help.
    """

    def __init__(self, shortcuts: Optional[Dict[str, str]] = None):
        self.shortcuts = shortcuts or {
            "Ctrl+C": "Cancel/Exit",
            "Ctrl+R": "Refresh",
            "j/k": "Scroll down/up",
            "q": "Quit",
            "?": "Toggle help",
        }

    def render(self) -> Panel:
        """Render the help panel."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="cyan bold")
        table.add_column("Action", style="dim")

        for key, action in self.shortcuts.items():
            table.add_row(key, action)

        return Panel(
            table,
            title="[bold]Keyboard Shortcuts[/bold]",
            border_style="green",
        )
