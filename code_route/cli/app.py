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

        # Tool events
        async def on_tool_start(event: "Event"):
            self.tool_list.add(ToolExecution(
                name=event.data.get("tool_name", "unknown"),
                status=ToolStatus.RUNNING,
                input_summary=str(event.data.get("input", ""))[:100],
                started_at=datetime.now(),
            ))
            self.status_bar.set_status(f"Running: {event.data.get('tool_name')}")

        async def on_tool_complete(event: "Event"):
            self.tool_list.update(
                event.data.get("tool_name", "unknown"),
                status=ToolStatus.SUCCESS,
                output_summary=str(event.data.get("result", ""))[:100],
                completed_at=datetime.now(),
                duration_ms=event.data.get("duration_ms"),
            )
            self.status_bar.set_status("Ready")

        async def on_tool_error(event: "Event"):
            self.tool_list.update(
                event.data.get("tool_name", "unknown"),
                status=ToolStatus.ERROR,
                error=str(event.data.get("error", "Unknown error")),
            )

        # Agent events
        async def on_agent_start(event: "Event"):
            self.agent_panel.update_status(
                event.data.get("agent_name", "unknown"),
                status="working",
                task=event.data.get("task", ""),
            )

        async def on_agent_complete(event: "Event"):
            self.agent_panel.update_status(
                event.data.get("agent_name", "unknown"),
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
        elif cmd == "/search":
            await self._search_history(args)
        elif cmd == "/context":
            await self._show_context()
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
    from ..core.events import EventBus

    event_bus = EventBus()
    config = config or AppConfig()

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

    app = CodeRouteApp(
        config=config,
        provider=provider,
        event_bus=event_bus,
        session_manager=session_manager,
    )

    if provider:
        from ..core.types import Message, MessageRole, ToolSchema, ToolCall
        from typing import AsyncIterator
        import json

        # Load available tools
        tools = {}
        try:
            from ..tools.bashtool import BashTool
            from ..tools.filecontentreadertool import FileContentReaderTool
            from ..tools.lstool import LSTool
            from ..tools.globtool import GlobTool
            from ..tools.greptool import GrepTool
            from ..tools.filecreatortool import FileCreatorTool
            from ..tools.fileedittool import FileEditTool

            tool_instances = [
                BashTool(),
                FileContentReaderTool(),
                LSTool(),
                GlobTool(),
                GrepTool(),
                FileCreatorTool(),
                FileEditTool(),
            ]
            tools = {t.name: t for t in tool_instances}
            Console().print(f"[dim]Loaded {len(tools)} tools: {', '.join(tools.keys())}[/dim]\n")
        except Exception as e:
            Console().print(f"[yellow]Warning: Could not load tools: {e}[/yellow]")

        # Build tool schemas for LLM
        tool_schemas = [
            ToolSchema(
                name=t.name,
                description=t.description,
                parameters=t.input_schema
            )
            for t in tools.values()
        ] if tools else None

        async def build_messages(user_input: str) -> list:
            """Build context messages."""
            if session_manager and session_manager.is_active:
                return await session_manager.build_context(
                    current_query=user_input,
                    system_prompt=app._system_prompt,
                )
            else:
                return [
                    Message(role=MessageRole.SYSTEM, content=app._system_prompt),
                    Message(role=MessageRole.USER, content=user_input),
                ]

        async def execute_tool(name: str, arguments: dict) -> str:
            """Execute a tool and return result."""
            if name not in tools:
                return f"Error: Unknown tool '{name}'"
            try:
                tool = tools[name]
                # Handle both sync and async execute
                result = tool.execute(**arguments)
                if hasattr(result, '__await__'):
                    result = await result
                return str(result) if result else "Tool executed successfully"
            except Exception as e:
                return f"Error executing {name}: {e}"

        # Agentic handler - executes tools in a loop
        async def handle_message(user_input: str) -> str:
            """Agentic response with tool execution."""
            messages = await build_messages(user_input)
            max_iterations = 10
            iteration = 0
            final_response = ""

            while iteration < max_iterations:
                iteration += 1

                # Get LLM response with tools
                response = await provider.complete(
                    messages,
                    tools=tool_schemas,
                    max_tokens=4096,
                )

                # Update token panel
                if response.usage:
                    app.token_panel.add(
                        input_tokens=response.usage.prompt_tokens,
                        output_tokens=response.usage.completion_tokens,
                    )

                # Check for tool calls
                if response.tool_calls:
                    # Show what the assistant said
                    if response.content:
                        Console().print(f"[cyan]{response.content}[/cyan]")

                    # Add assistant message with ALL tool calls first
                    messages.append(Message(
                        role=MessageRole.ASSISTANT,
                        content=response.content or "",
                        tool_calls=response.tool_calls,
                    ))

                    # Execute each tool call and add results
                    for tc in response.tool_calls:
                        Console().print(f"\n[yellow]▶ Executing {tc.name}...[/yellow]")
                        result = await execute_tool(tc.name, tc.arguments)
                        # Truncate long results for display
                        display_result = result[:500] + "..." if len(result) > 500 else result
                        Console().print(f"[dim]{display_result}[/dim]")

                        # Add tool result
                        messages.append(Message(
                            role=MessageRole.TOOL,
                            content=result,
                            tool_call_id=tc.id,
                            name=tc.name,
                        ))

                    continue  # Loop for more tool calls

                # No tool calls - final response
                final_response = response.content
                break

            return final_response

        # Register handler
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
    if args.provider or args.model:
        from ..providers import get_provider

        provider = get_provider(args.provider, args.model)
        Console().print(f"[cyan]Using {provider.name}: {provider._model}[/cyan]\n")

    asyncio.run(run_app(provider=provider))


if __name__ == "__main__":
    main()
