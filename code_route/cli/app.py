"""
Code Route CLI Application.

Main async application that combines streaming,
panels, input handling, and event-driven updates.

Features:
- Persistent conversations across sessions
- RAG-enhanced context from past conversations
- Project-aware context (CLAUDE.md, README.md)
- Session management and history
"""

import asyncio
import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from rich.markdown import Markdown
from rich.align import Align
from rich.table import Table
from rich.tree import Tree

from .streaming import StreamingRenderer, ThinkingIndicator
from .panels import (
    ToolPanel,
    ToolExecution,
    ToolExecutionList,
    ToolStatus,
    AgentPanel,
    AgentNode,
    TokenUsagePanel,
    StatusBar,
    ConversationPanel,
    HelpPanel,
)
from .keybindings import KeyBindings, KeyCode, create_default_bindings

if TYPE_CHECKING:
    from ..core.events import EventBus, Event
    from ..providers.base import BaseProvider
    from ..memory.session import SessionManager


def _load_legacy_cli_module():
    """Load the legacy `code_route/cli.py` module despite package name collision."""
    legacy_path = Path(__file__).resolve().parents[1] / "cli.py"
    if not legacy_path.exists():
        return None

    spec = importlib.util.spec_from_file_location("code_route._legacy_cli", legacy_path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def app_system_prompt(
    config: "AppConfig",
    session_manager: Optional["SessionManager"],
) -> str:
    """Build a stable system prompt outside the TUI runtime."""
    base_prompt = """You are Code Route, an intelligent coding assistant.

You help users with:
- Writing and reviewing code
- Debugging and fixing issues
- Understanding codebases
- Answering technical questions

Be concise, accurate, and helpful. When showing code, use appropriate markdown formatting."""

    if session_manager and session_manager.project_context:
        ctx = session_manager.project_context
        base_prompt += "\n\n## Current Project\n"
        base_prompt += f"**Name**: {ctx.name}\n"
        base_prompt += f"**Path**: {ctx.path}\n"
        if ctx.branch:
            base_prompt += f"**Git Branch**: {ctx.branch}\n"
        if ctx.context_content:
            content = ctx.context_content
            if len(content) > 3000:
                content = content[:3000] + "\n\n...(truncated)"
            base_prompt += f"\n**Project Guidelines**:\n{content}"

    return base_prompt


@dataclass
class AppState:
    """Application state."""
    running: bool = True
    show_help: bool = False
    show_tools: bool = True
    show_agents: bool = True
    show_tokens: bool = True
    scroll_offset: int = 0
    current_conversation_id: Optional[str] = None
    input_mode: bool = True  # Whether accepting user input


@dataclass
class AppConfig:
    """Application configuration."""
    model: str = ""
    provider: str = ""
    max_tokens: int = 200000
    show_thinking: bool = True
    auto_save: bool = True
    project_path: Optional[str] = None
    enable_rag: bool = False  # Disabled by default - slow embedding loading
    enable_persistence: bool = True
    tool_profile: str = "coding"
    json_mode: bool = False


class CodeRouteApp:
    """
    Main Code Route CLI application.

    Provides a rich terminal interface with:
    - Streaming assistant responses
    - Tool execution visualization
    - Agent hierarchy display
    - Token usage tracking
    - Keyboard navigation

    Usage:
        app = CodeRouteApp()
        await app.run()
    """

    BANNER = """
[bold bright_blue]
   ____          _        ____             _
  / ___|___   __| | ___  |  _ \\ ___  _   _| |_ ___
 | |   / _ \\ / _` |/ _ \\ | |_) / _ \\| | | | __/ _ \\
 | |__| (_) | (_| |  __/ |  _ < (_) | |_| | ||  __/
  \\____\\___/ \\__,_|\\___| |_| \\_\\___/ \\__,_|\\__\\___|
[/bold bright_blue]
[dim]AI Assistant with Multi-Agent Architecture[/dim]
"""

    def __init__(
        self,
        console: Optional[Console] = None,
        config: Optional[AppConfig] = None,
        provider: Optional["BaseProvider"] = None,
        event_bus: Optional["EventBus"] = None,
        session_manager: Optional["SessionManager"] = None,
    ):
        self.console = console or Console()
        self.config = config or AppConfig()
        self.provider = provider
        self.event_bus = event_bus
        self.session_manager = session_manager

        # State
        self.state = AppState()

        # UI Components
        self.streaming_renderer = StreamingRenderer(
            console=self.console,
            panel_title="Assistant",
        )
        self.tool_list = ToolExecutionList()
        self.agent_panel = AgentPanel()
        self.token_panel = TokenUsagePanel(max_tokens=self.config.max_tokens)
        self.status_bar = StatusBar(
            model=self.config.model,
            provider=self.config.provider,
        )
        self.conversation_panel = ConversationPanel()
        self.help_panel = HelpPanel()

        # Key bindings
        self.bindings = self._setup_bindings()

        # Callbacks
        self._on_message: Optional[Callable[[str], asyncio.Future]] = None
        self._on_stream: Optional[Callable[[str], asyncio.Future]] = None

        # System prompt
        self._system_prompt = self._build_system_prompt()

    def _setup_bindings(self) -> KeyBindings:
        """Set up key bindings."""
        bindings = create_default_bindings()

        # Override handlers with actual implementations
        bindings.bind(
            self._scroll_down,
            char="j",
            description="Scroll down",
        )
        bindings.bind(
            self._scroll_up,
            char="k",
            description="Scroll up",
        )
        bindings.bind(
            self._toggle_help,
            char="?",
            description="Toggle help",
        )
        bindings.bind(
            self._quit,
            char="q",
            description="Quit",
        )
        bindings.bind(
            self._cancel,
            ctrl=True,
            key=KeyCode.CTRL_C,
            description="Cancel/Interrupt",
        )
        bindings.bind(
            self._refresh,
            ctrl=True,
            key=KeyCode.CTRL_R,
            description="Refresh display",
        )
        bindings.bind(
            self._toggle_tools,
            char="t",
            description="Toggle tool panel",
        )
        bindings.bind(
            self._toggle_agents,
            char="a",
            description="Toggle agent panel",
        )

        return bindings

    def _scroll_down(self) -> None:
        """Scroll down."""
        self.state.scroll_offset += 1

    def _scroll_up(self) -> None:
        """Scroll up."""
        self.state.scroll_offset = max(0, self.state.scroll_offset - 1)

    def _toggle_help(self) -> None:
        """Toggle help panel."""
        self.state.show_help = not self.state.show_help

    def _quit(self) -> None:
        """Quit the application."""
        self.state.running = False

    def _cancel(self) -> None:
        """Cancel current operation."""
        self.streaming_renderer.pause()
        self.status_bar.set_status("Cancelled")

    def _refresh(self) -> None:
        """Refresh the display."""
        self.console.clear()

    def _toggle_tools(self) -> None:
        """Toggle tool panel visibility."""
        self.state.show_tools = not self.state.show_tools

    def _toggle_agents(self) -> None:
        """Toggle agent panel visibility."""
        self.state.show_agents = not self.state.show_agents

    def on_message(self, callback: Callable[[str], asyncio.Future]) -> None:
        """Register message handler (non-streaming)."""
        self._on_message = callback

    def on_stream(self, callback: Callable[[str], asyncio.Future]) -> None:
        """Register streaming handler. Takes precedence over on_message."""
        self._on_stream = callback

    def _build_system_prompt(self) -> str:
        """Build the system prompt with project context."""
        base_prompt = """You are Code Route, an intelligent coding assistant.

You help users with:
- Writing and reviewing code
- Debugging and fixing issues
- Understanding codebases
- Answering technical questions

Be concise, accurate, and helpful. When showing code, use appropriate markdown formatting."""

        # Add project context if available
        if self.session_manager and self.session_manager.project_context:
            ctx = self.session_manager.project_context
            base_prompt += f"\n\n## Current Project\n"
            base_prompt += f"**Name**: {ctx.name}\n"
            base_prompt += f"**Path**: {ctx.path}\n"

            if ctx.branch:
                base_prompt += f"**Git Branch**: {ctx.branch}\n"

            if ctx.context_content:
                # Truncate if too long
                content = ctx.context_content
                if len(content) > 3000:
                    content = content[:3000] + "\n\n...(truncated)"
                base_prompt += f"\n**Project Guidelines**:\n{content}"

        return base_prompt

    async def _initialize_session(self) -> None:
        """Initialize the session manager."""
        if not self.session_manager:
            return

        project_path = self.config.project_path or os.getcwd()

        self.status_bar.set_status("Initializing session...")

        conv_id = await self.session_manager.start(project_path=project_path)
        self.state.current_conversation_id = conv_id

        # Update system prompt with project context
        self._system_prompt = self._build_system_prompt()

        # Show session info
        session_info = await self.session_manager.get_session_info()
        if session_info:
            msg_count = session_info.message_count
            if msg_count > 0:
                self.console.print(
                    f"[dim]Resumed session with {msg_count} messages[/dim]"
                )

                # Show last few messages as context
                if self.session_manager._messages_cache:
                    recent = self.session_manager._messages_cache[-4:]
                    for msg in recent:
                        role = "You" if msg.role.value == "user" else "Assistant"
                        content = msg.content
                        if len(content) > 100:
                            content = content[:100] + "..."
                        self.conversation_panel.add(msg.role.value, content)
            else:
                self.console.print("[dim]Starting new session[/dim]")

        if self.session_manager.project_context:
            ctx = self.session_manager.project_context
            project_info = f"[dim]Project: {ctx.name}"
            if ctx.branch:
                project_info += f" ({ctx.branch})"
            if ctx.context_file:
                project_info += f" - {ctx.context_file} loaded"
            project_info += "[/dim]"
            self.console.print(project_info)

        self.status_bar.set_status("Ready")

    async def _setup_event_handlers(self) -> None:
        """Set up event bus handlers."""
        if not self.event_bus:
            return

        from ..core.events import EventType

        def _first(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
            for key in keys:
                value = data.get(key)
                if value is not None:
                    return value
            return default

        def _find_agent(node: AgentNode, name: str) -> Optional[AgentNode]:
            if node.name == name:
                return node
            for child in node.children:
                match = _find_agent(child, name)
                if match:
                    return match
            return None

        def _ensure_agent_node(agent_name: str, role: str) -> None:
            if self.agent_panel.root is None:
                self.agent_panel.set_root(AgentNode(name=agent_name, role=role))
                return
            if _find_agent(self.agent_panel.root, agent_name):
                return
            self.agent_panel.root.children.append(
                AgentNode(name=agent_name, role=role)
            )

        # Tool events
        async def on_tool_start(event: "Event"):
            tool_name = str(
                _first(event.data, "tool_name", "tool", default="unknown")
            )
            tool_input = _first(event.data, "input", "args", default="")
            self.tool_list.add(ToolExecution(
                name=tool_name,
                status=ToolStatus.RUNNING,
                input_summary=str(tool_input)[:100],
                started_at=datetime.now(),
            ))
            self.status_bar.set_status(f"Running: {tool_name}")

        async def on_tool_complete(event: "Event"):
            tool_name = str(
                _first(event.data, "tool_name", "tool", default="unknown")
            )
            tool_result = _first(event.data, "result")
            tool_succeeded = bool(event.data.get("success", True))
            if event.data.get("error") is not None:
                tool_succeeded = False
            if tool_result is None and "success" in event.data:
                tool_result = "success" if event.data.get("success") else "failed"
            self.tool_list.update(
                tool_name,
                status=ToolStatus.SUCCESS if tool_succeeded else ToolStatus.ERROR,
                output_summary=str(tool_result or "")[:100],
                error=str(event.data.get("error", ""))[:200] if not tool_succeeded else None,
                completed_at=datetime.now(),
                duration_ms=event.data.get("duration_ms"),
            )
            self.status_bar.set_status("Ready")

        async def on_tool_error(event: "Event"):
            tool_name = str(
                _first(event.data, "tool_name", "tool", default="unknown")
            )
            self.tool_list.update(
                tool_name,
                status=ToolStatus.ERROR,
                error=str(event.data.get("error", "Unknown error")),
            )

        # Agent events
        async def on_agent_start(event: "Event"):
            agent_name = str(
                _first(event.data, "agent_name", "agent", default="unknown")
            )
            agent_role = str(_first(event.data, "agent_role", "agent", default="agent"))
            task_text = str(_first(event.data, "task", "description", default=""))
            _ensure_agent_node(agent_name, agent_role)
            self.agent_panel.update_status(
                agent_name,
                status="working",
                task=task_text,
            )

        async def on_agent_complete(event: "Event"):
            agent_name = str(
                _first(event.data, "agent_name", "agent", default="unknown")
            )
            agent_role = str(_first(event.data, "agent_role", "agent", default="agent"))
            _ensure_agent_node(agent_name, agent_role)
            self.agent_panel.update_status(
                agent_name,
                status="complete",
            )

        # Token events
        async def on_tokens_used(event: "Event"):
            self.token_panel.add(
                input_tokens=event.data.get("input_tokens", 0),
                output_tokens=event.data.get("output_tokens", 0),
            )

        # Subscribe to events
        self.event_bus.subscribe(EventType.TOOL_STARTED, on_tool_start)
        self.event_bus.subscribe(EventType.TOOL_COMPLETED, on_tool_complete)
        self.event_bus.subscribe(EventType.TOOL_ERROR, on_tool_error)
        self.event_bus.subscribe(EventType.AGENT_STARTED, on_agent_start)
        self.event_bus.subscribe(EventType.AGENT_COMPLETED, on_agent_complete)
        self.event_bus.subscribe(EventType.STREAM_TOKEN, on_tokens_used)

    def _build_layout(self) -> Layout:
        """Build the application layout."""
        layout = Layout()

        # Main structure
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        # Body split
        body = layout["body"]

        if self.state.show_tools or self.state.show_agents:
            body.split_row(
                Layout(name="main", ratio=3),
                Layout(name="sidebar", ratio=1),
            )

            # Sidebar components
            sidebar_parts = []
            if self.state.show_agents:
                sidebar_parts.append(Layout(self.agent_panel.render(), name="agents"))
            if self.state.show_tools:
                sidebar_parts.append(Layout(self.tool_list.render(), name="tools"))
            if self.state.show_tokens:
                sidebar_parts.append(Layout(self.token_panel.render(), name="tokens", size=8))

            if sidebar_parts:
                layout["sidebar"].split_column(*sidebar_parts)
        else:
            body.update(Layout(name="main"))

        return layout

    def _render_header(self) -> Panel:
        """Render the header."""
        header_text = Text()
        header_text.append("Code Route", style="bold bright_blue")
        header_text.append(" | ", style="dim")
        header_text.append(self.config.model or "No model", style="cyan")

        return Panel(
            Align.center(header_text),
            style="dim",
            padding=(0, 0),
        )

    def show_banner(self) -> None:
        """Display the welcome banner."""
        self.console.print(self.BANNER)

    async def prompt_user(self, prompt: str = "You") -> str:
        """
        Prompt user for input.

        Args:
            prompt: Prompt text

        Returns:
            User input
        """
        self.console.print()
        return Prompt.ask(f"[bold cyan]{prompt}[/bold cyan]")

    async def show_response(self, response: str) -> None:
        """
        Display an assistant response (non-streaming).

        Args:
            response: Response text
        """
        self.console.print()
        self.console.print(Panel(
            Markdown(response),
            title="[bold cyan]Assistant[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        ))

    async def stream_response(self, tokens) -> str:
        """
        Stream a response token by token with live display.

        Args:
            tokens: Async iterator of tokens

        Returns:
            Complete response
        """
        self.console.print()  # Add spacing

        # Track tokens for panel update
        token_count = 0

        async with self.streaming_renderer.stream() as stream:
            async for token in tokens:
                await stream.push(token)
                token_count += 1

                # Update token panel periodically
                if token_count % 10 == 0:
                    self.token_panel.add(output_tokens=10)

        return self.streaming_renderer.buffer.content

    async def show_tool_execution(
        self,
        name: str,
        input_data: Any,
        result: Any,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Display a tool execution."""
        execution = ToolExecution(
            name=name,
            status=ToolStatus.ERROR if error else ToolStatus.SUCCESS,
            input_summary=str(input_data)[:100],
            output_summary=str(result)[:100] if result else "",
            duration_ms=duration_ms,
            error=error,
        )
        self.console.print(ToolPanel(execution).render())

    async def show_thinking(self, message: str = "Thinking") -> ThinkingIndicator:
        """Show a thinking indicator."""
        return ThinkingIndicator(self.console, message)

    async def run_conversation_loop(self) -> None:
        """Run the main conversation loop."""
        self.show_banner()

        # Initialize session for persistence
        await self._initialize_session()

        while self.state.running:
            try:
                # Get user input
                user_input = await self.prompt_user()

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    await self._handle_command(user_input)
                    continue

                # Add to conversation panel
                self.conversation_panel.add("user", user_input)

                # Save to session (persistence)
                if self.session_manager:
                    await self.session_manager.add_user_message(user_input)

                # Process message
                if self._on_stream:
                    # Streaming mode
                    self.status_bar.set_status("Generating...")

                    try:
                        # _on_stream returns an async generator, not a coroutine
                        tokens = self._on_stream(user_input)
                        response = await self.stream_response(tokens)

                        if response:
                            self.conversation_panel.add("assistant", response[:200] + "..." if len(response) > 200 else response)

                            # Save response to session (persistence)
                            if self.session_manager:
                                await self.session_manager.add_assistant_message(response)

                    except Exception as e:
                        self.console.print(f"[red]Error: {e}[/red]")

                    self.status_bar.set_status("Ready")

                elif self._on_message:
                    # Non-streaming fallback
                    self.status_bar.set_status("Processing...")

                    with ThinkingIndicator(self.console, "Thinking..."):
                        response = await self._on_message(user_input)

                    if response:
                        await self.show_response(response)
                        self.conversation_panel.add("assistant", response)

                        # Save response to session (persistence)
                        if self.session_manager:
                            await self.session_manager.add_assistant_message(response)

                    self.status_bar.set_status("Ready")
                else:
                    self.console.print(
                        "[yellow]No message handler configured[/yellow]"
                    )

            except KeyboardInterrupt:
                self.console.print("\n[dim]Use /quit or Ctrl+D to exit[/dim]")
            except EOFError:
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")

        self.console.print("\n[bold blue]Goodbye![/bold blue]")

    async def _handle_command(self, command: str) -> None:
        """Handle a slash command."""
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit", "/q"):
            self.state.running = False
        elif cmd == "/help":
            self._show_help()
        elif cmd == "/clear":
            self.console.clear()
            self.conversation_panel.clear()
        elif cmd == "/tools":
            self.console.print(self.tool_list.render())
        elif cmd == "/tokens":
            self.console.print(self.token_panel.render())
        elif cmd == "/status":
            self.console.print(self.status_bar.render())
        elif cmd == "/sessions":
            await self._show_sessions()
        elif cmd == "/history":
            await self._show_history(args)
        elif cmd == "/resume":
            await self._resume_session(args)
        elif cmd == "/new":
            await self._new_session()
        elif cmd == "/branch":
            await self._branch_session(args)
        elif cmd == "/search":
            await self._search_history(args)
        elif cmd == "/context":
            await self._show_context()
        elif cmd == "/tree":
            await self._show_session_tree()
        else:
            self.console.print(f"[yellow]Unknown command: {command}[/yellow]")
            self._show_help()

    async def _show_sessions(self) -> None:
        """Show available sessions."""
        if not self.session_manager:
            self.console.print("[yellow]Session management not enabled[/yellow]")
            return

        sessions = await self.session_manager.list_sessions(limit=20)

        if not sessions:
            self.console.print("[dim]No sessions found[/dim]")
            return

        table = Table(title="Sessions", show_header=True, header_style="bold cyan")
        table.add_column("ID", style="dim", width=12)
        table.add_column("Project", style="green")
        table.add_column("Messages", justify="right")
        table.add_column("Last Updated", style="dim")
        table.add_column("", width=3)

        for session in sessions:
            is_current = session.id == self.state.current_conversation_id
            project = Path(session.project_path).name if session.project_path else "Unknown"
            updated = session.updated_at.strftime("%Y-%m-%d %H:%M")

            table.add_row(
                session.id[:8] + "...",
                project,
                str(session.message_count),
                updated,
                "[bold green]*[/bold green]" if is_current else "",
            )

        self.console.print(table)
        self.console.print("\n[dim]Use /resume <id> to switch sessions[/dim]")

    async def _show_history(self, args: str) -> None:
        """Show conversation history."""
        if not self.session_manager:
            self.console.print("[yellow]Session management not enabled[/yellow]")
            return

        limit = 20
        if args:
            try:
                limit = int(args)
            except ValueError:
                pass

        messages = self.session_manager._messages_cache[-limit:]

        if not messages:
            self.console.print("[dim]No messages in current session[/dim]")
            return

        self.console.print(f"\n[bold]Last {len(messages)} messages:[/bold]\n")

        for msg in messages:
            role = "[cyan]You[/cyan]" if msg.role.value == "user" else "[magenta]Assistant[/magenta]"
            content = msg.content
            if len(content) > 200:
                content = content[:200] + "..."
            self.console.print(f"{role}: {content}\n")

    async def _resume_session(self, session_id: str) -> None:
        """Resume a previous session."""
        if not self.session_manager:
            self.console.print("[yellow]Session management not enabled[/yellow]")
            return

        if not session_id:
            self.console.print("[yellow]Usage: /resume <session_id>[/yellow]")
            return

        # Find matching session
        sessions = await self.session_manager.list_sessions(limit=100)
        matching = [s for s in sessions if s.id.startswith(session_id)]

        if not matching:
            self.console.print(f"[red]Session not found: {session_id}[/red]")
            return

        if len(matching) > 1:
            self.console.print(f"[yellow]Multiple matches, be more specific[/yellow]")
            return

        session = matching[0]
        success = await self.session_manager.switch_session(session.id)

        if success:
            self.state.current_conversation_id = session.id
            self._system_prompt = self._build_system_prompt()
            self.console.print(f"[green]Resumed session {session.id[:8]}... ({session.message_count} messages)[/green]")

            # Show recent context
            if self.session_manager._messages_cache:
                recent = self.session_manager._messages_cache[-2:]
                for msg in recent:
                    content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                    self.conversation_panel.add(msg.role.value, content)
        else:
            self.console.print(f"[red]Failed to resume session[/red]")

    async def _new_session(self) -> None:
        """Start a new session."""
        if not self.session_manager:
            self.console.print("[yellow]Session management not enabled[/yellow]")
            return

        project_path = self.config.project_path or os.getcwd()
        conv_id = await self.session_manager.start(project_path=project_path, force_new=True)
        self.state.current_conversation_id = conv_id
        self.conversation_panel.clear()
        self._system_prompt = self._build_system_prompt()

        self.console.print(f"[green]Started new session: {conv_id[:8]}...[/green]")

    async def _branch_session(self, title: str) -> None:
        """Create and switch to a child branch of the current session."""
        if not self.session_manager:
            self.console.print("[yellow]Session management not enabled[/yellow]")
            return

        branch_title = title.strip() if title else None
        conv_id = await self.session_manager.branch_session(title=branch_title)
        self.state.current_conversation_id = conv_id
        self.conversation_panel.clear()
        self._system_prompt = self._build_system_prompt()
        label = branch_title or conv_id[:8]
        self.console.print(f"[green]Created branch session: {label} ({conv_id[:8]}...)[/green]")

    async def _show_session_tree(self) -> None:
        """Show branch tree for project sessions."""
        if not self.session_manager:
            self.console.print("[yellow]Session management not enabled[/yellow]")
            return

        project_path = None
        if self.session_manager.project_context:
            project_path = self.session_manager.project_context.path

        tree_data = await self.session_manager.get_session_tree(project_path=project_path)
        if not tree_data:
            self.console.print("[dim]No sessions found[/dim]")
            return

        root = Tree("Sessions")

        def add_node(parent: Tree, node: Dict[str, Any]) -> None:
            current = node["id"] == self.state.current_conversation_id
            prefix = "* " if current else ""
            label = (
                f"{prefix}{node['title']} "
                f"[dim]({node['id'][:8]}..., {node['message_count']} msgs)[/dim]"
            )
            branch = parent.add(label)
            for child in node["children"]:
                add_node(branch, child)

        for node in tree_data:
            add_node(root, node)

        self.console.print(root)

    async def _search_history(self, query: str) -> None:
        """Search past conversations using RAG."""
        if not self.session_manager:
            self.console.print("[yellow]Session management not enabled[/yellow]")
            return

        if not query:
            self.console.print("[yellow]Usage: /search <query>[/yellow]")
            return

        self.status_bar.set_status("Searching...")

        results = await self.session_manager.search_history(query, top_k=10)

        self.status_bar.set_status("Ready")

        if not results:
            self.console.print(f"[dim]No results for: {query}[/dim]")
            return

        self.console.print(f"\n[bold]Search results for '{query}':[/bold]\n")

        for i, result in enumerate(results, 1):
            similarity = int(result.similarity * 100)
            text = result.text
            if len(text) > 150:
                text = text[:150] + "..."

            self.console.print(f"[cyan]{i}.[/cyan] [{similarity}%] {text}\n")

    async def _show_context(self) -> None:
        """Show current project context."""
        if not self.session_manager or not self.session_manager.project_context:
            self.console.print("[dim]No project context available[/dim]")
            return

        ctx = self.session_manager.project_context
        self.console.print(Panel(
            ctx.to_prompt(),
            title="[bold]Project Context[/bold]",
            border_style="green",
        ))

    def _show_help(self) -> None:
        """Show help information."""
        help_text = """
[bold]Available Commands:[/bold]

  [cyan]General:[/cyan]
  /help       - Show this help
  /quit       - Exit the application
  /clear      - Clear the screen
  /status     - Show current status

  [cyan]Session Management:[/cyan]
  /sessions   - List available sessions
  /resume <id> - Resume a previous session
  /new        - Start a new session
  /branch [name] - Create a child session branch
  /tree       - Show branched session tree
  /history    - Show conversation history

  [cyan]Search & Context:[/cyan]
  /search <q> - Search past conversations (RAG)
  /context    - Show project context

  [cyan]Display:[/cyan]
  /tools      - Show tool executions
  /tokens     - Show token usage

[bold]Keyboard Shortcuts:[/bold]
  Ctrl+C    - Cancel current operation
  Ctrl+D    - Exit
"""
        self.console.print(Panel(
            help_text,
            title="[bold]Help[/bold]",
            border_style="green",
        ))

    async def run(self) -> None:
        """Run the application."""
        await self._setup_event_handlers()
        await self.run_conversation_loop()


async def run_app(
    provider: Optional["BaseProvider"] = None,
    config: Optional[AppConfig] = None,
    enable_persistence: bool = True,
) -> None:
    """
    Convenience function to run the CLI app.

    Args:
        provider: LLM provider to use
        config: App configuration
        enable_persistence: Enable session persistence and RAG
    """
    from ..coding_agent import CodingAgent, make_json_event_sink
    from ..core.events import EventBus
    from ..core.types import Message, MessageRole
    from ..providers import get_provider
    from ..tools import get_tools_for_profile

    event_bus = EventBus()
    config = config or AppConfig()

    if provider is None:
        try:
            provider = get_provider(
                provider_name=config.provider or None,
                model=config.model or None,
            )
        except Exception as exc:
            Console().print(f"[red]No provider available: {exc}[/red]")
            return

    config.provider = config.provider or provider.name
    if not config.model:
        config.model = getattr(provider, "_model", "")

    # Initialize session manager for persistence
    session_manager = None
    if enable_persistence and config.enable_persistence:
        try:
            from ..memory.session import SessionManager, SessionConfig

            session_config = SessionConfig(
                enable_rag=config.enable_rag,
            )
            session_manager = SessionManager(session_config)
        except Exception as e:
            # Fall back to no persistence if it fails
            Console().print(f"[yellow]Warning: Session persistence disabled: {e}[/yellow]")

    # Load tools from profile
    try:
        tool_instances = get_tools_for_profile(config.tool_profile)
        Console().print(
            f"[dim]Tool profile '{config.tool_profile}': "
            f"{len(tool_instances)} tools loaded[/dim]"
        )
    except Exception as exc:
        Console().print(f"[yellow]Falling back to full tool set: {exc}[/yellow]")
        tool_instances = get_tools_for_profile("full")

    # Keep short-term history when persistence is disabled/unavailable.
    transient_history: List[Message] = []

    def _preview_text(value: Any, max_chars: int = 160) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            text = value
        else:
            try:
                text = json.dumps(value, ensure_ascii=True, default=str)
            except Exception:
                text = str(value)
        if len(text) > max_chars:
            return text[: max_chars - 3] + "..."
        return text

    if config.json_mode:
        sink = make_json_event_sink()
        agent = CodingAgent(provider, tool_instances, event_sink=sink)

        # Ensure session is ready for persistence in JSON mode as well.
        if session_manager and not session_manager.is_active:
            await session_manager.start(project_path=config.project_path or os.getcwd())

        sink(
            {
                "type": "session.started",
                "timestamp": datetime.now().timestamp(),
                "payload": {
                    "model": config.model,
                    "provider": config.provider,
                    "tool_profile": config.tool_profile,
                },
            }
        )

        while True:
            try:
                user_input = input().strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input in {"/quit", "/exit", "/q"}:
                break

            sink(
                {
                    "type": "user.message",
                    "timestamp": datetime.now().timestamp(),
                    "payload": {"content": user_input},
                }
            )

            if session_manager and session_manager.is_active:
                await session_manager.add_user_message(user_input)
                messages = [
                    Message(role=MessageRole.SYSTEM, content=app_system_prompt(config, session_manager)),
                    *session_manager.get_messages(),
                ]
            else:
                transient_history.append(Message(role=MessageRole.USER, content=user_input))
                messages = [
                    Message(role=MessageRole.SYSTEM, content=app_system_prompt(config, None)),
                    *transient_history,
                ]

            result = await agent.run(messages)
            if session_manager and session_manager.is_active:
                await session_manager.add_assistant_message(result.content)
            else:
                transient_history.append(
                    Message(role=MessageRole.ASSISTANT, content=result.content)
                )

            sink(
                {
                    "type": "assistant.message",
                    "timestamp": datetime.now().timestamp(),
                    "payload": {
                        "content": result.content,
                        "usage": {
                            "prompt_tokens": result.usage.prompt_tokens,
                            "completion_tokens": result.usage.completion_tokens,
                            "total_tokens": result.usage.total_tokens,
                        },
                        "iterations": result.iterations,
                        "tool_calls": result.tool_calls,
                    },
                }
            )
        return

    app = CodeRouteApp(
        config=config,
        provider=provider,
        event_bus=event_bus,
        session_manager=session_manager,
    )

    tool_call_labels: Dict[str, str] = {}

    async def ui_event_sink(event: Dict[str, Any]) -> None:
        event_type = event.get("type")
        payload = event.get("payload", {})

        if event_type == "assistant.iteration.started":
            app.status_bar.set_status("Thinking...")
            return

        if event_type == "tool.call.started":
            tool_name = str(payload.get("name", "tool"))
            tool_id = str(payload.get("id") or f"{tool_name}-{len(tool_call_labels) + 1}")
            label = f"{tool_name}#{tool_id[:6]}"
            tool_call_labels[tool_id] = label
            app.tool_list.add(
                ToolExecution(
                    name=label,
                    status=ToolStatus.RUNNING,
                    input_summary=_preview_text(payload.get("arguments")),
                    started_at=datetime.now(),
                )
            )
            app.status_bar.set_status(f"Running: {tool_name}")
            return

        if event_type == "tool.call.completed":
            tool_name = str(payload.get("name", "tool"))
            tool_id = str(payload.get("id") or "")
            label = tool_call_labels.get(
                tool_id,
                f"{tool_name}#{tool_id[:6]}" if tool_id else tool_name,
            )
            app.tool_list.update(
                label,
                status=ToolStatus.SUCCESS if payload.get("success") else ToolStatus.ERROR,
                output_summary=_preview_text(payload.get("output_preview")),
                error=_preview_text(payload.get("error"), max_chars=240) if payload.get("error") else None,
                completed_at=datetime.now(),
                duration_ms=payload.get("elapsed_ms"),
            )
            app.status_bar.set_status("Ready")
            return

        if event_type == "assistant.completed":
            app.status_bar.set_status("Ready")
            return

        if event_type == "assistant.failed":
            app.status_bar.set_status("Max iterations reached")

    agent = CodingAgent(provider, tool_instances, event_sink=ui_event_sink)

    async def handle_message(user_input: str) -> str:
        """Single-agent coding handler."""
        if session_manager and session_manager.is_active:
            # User message is already persisted by the app loop before handler invocation.
            messages = [
                Message(role=MessageRole.SYSTEM, content=app._system_prompt),
                *session_manager.get_messages(),
            ]
        else:
            transient_history.append(Message(role=MessageRole.USER, content=user_input))
            messages = [
                Message(role=MessageRole.SYSTEM, content=app._system_prompt),
                *transient_history,
            ]

        result = await agent.run(messages)
        if not (session_manager and session_manager.is_active):
            transient_history.append(
                Message(role=MessageRole.ASSISTANT, content=result.content)
            )
        app.token_panel.add(
            input_tokens=result.usage.prompt_tokens,
            output_tokens=result.usage.completion_tokens,
        )
        return result.content

    app.on_message(handle_message)

    await app.run()


# Legacy CLI entry point for backwards compatibility
def main():
    """Legacy main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Code Route - AI Assistant with Multi-Agent Architecture",
    )
    parser.add_argument("--web", action="store_true", help="Launch web interface")
    parser.add_argument("--init", action="store_true", help="Initialize project")
    parser.add_argument("--tools", action="store_true", help="Show available tools")
    parser.add_argument("--status", action="store_true", help="Show system status")
    parser.add_argument("--version", action="store_true", help="Show version")
    parser.add_argument("--no-banner", action="store_true", help="Skip banner")
    parser.add_argument("--provider", "-p", type=str, help="LLM provider (anthropic, openai, cerebras, openrouter, local)")
    parser.add_argument("--model", "-m", type=str, help="Model to use (e.g., zai-glm-4.7, claude-sonnet-4)")
    parser.add_argument(
        "--profile",
        type=str,
        default="coding",
        help="Tool profile (coding, minimal, full)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON events (one per line) for automation",
    )

    args = parser.parse_args()

    legacy_cli = None
    try:
        legacy_cli = _load_legacy_cli_module()
    except Exception:
        legacy_cli = None

    if legacy_cli:
        if args.init:
            legacy_cli.init_project()
            return

        if args.status:
            legacy_cli.show_status()
            return

        if not args.no_banner:
            legacy_cli.show_banner()

        if args.tools:
            if legacy_cli.check_config():
                legacy_cli.show_tools()
            return

        if args.web:
            if legacy_cli.check_config():
                legacy_cli.launch_web()
            return

    # New-style startup
    provider = None
    app_config = AppConfig(
        model=args.model or "",
        provider=args.provider or "",
        tool_profile=args.profile,
        json_mode=args.json,
    )

    if args.provider or args.model:
        from ..providers import get_provider

        provider = get_provider(args.provider, args.model)
        Console().print(f"[cyan]Using {provider.name}: {provider._model}[/cyan]\n")

    asyncio.run(run_app(provider=provider, config=app_config))


if __name__ == "__main__":
    main()
