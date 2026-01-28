"""
Code Route CLI Application.

Main async application that combines streaming,
panels, input handling, and event-driven updates.
"""

import asyncio
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
    from ..memory.context import ConversationManager


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
        conversation_manager: Optional["ConversationManager"] = None,
    ):
        self.console = console or Console()
        self.config = config or AppConfig()
        self.provider = provider
        self.event_bus = event_bus
        self.conversation_manager = conversation_manager

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
        """Register message handler."""
        self._on_message = callback

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
        self.event_bus.subscribe(EventType.STREAM_CHUNK, on_tokens_used)

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
        Display an assistant response with streaming.

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
        Stream a response token by token.

        Args:
            tokens: Async iterator of tokens

        Returns:
            Complete response
        """
        return await self.streaming_renderer.stream_tokens(tokens)

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
        self.status_bar.set_status("Ready")

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

                # Add to conversation
                self.conversation_panel.add("user", user_input)

                # Process message
                if self._on_message:
                    self.status_bar.set_status("Processing...")

                    with ThinkingIndicator(self.console, "Thinking..."):
                        response = await self._on_message(user_input)

                    if response:
                        await self.show_response(response)
                        self.conversation_panel.add("assistant", response)

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
        cmd = command.lower().strip()

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
        else:
            self.console.print(f"[yellow]Unknown command: {command}[/yellow]")
            self._show_help()

    def _show_help(self) -> None:
        """Show help information."""
        help_text = """
[bold]Available Commands:[/bold]

  /help     - Show this help
  /quit     - Exit the application
  /clear    - Clear the screen
  /tools    - Show tool executions
  /tokens   - Show token usage
  /status   - Show current status

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
) -> None:
    """
    Convenience function to run the CLI app.

    Args:
        provider: LLM provider to use
        config: App configuration
    """
    from ..core.events import EventBus

    event_bus = EventBus()
    app = CodeRouteApp(
        config=config,
        provider=provider,
        event_bus=event_bus,
    )

    if provider:
        from ..core.types import Message, MessageRole

        async def handle_message(user_input: str) -> str:
            messages = [
                Message(role=MessageRole.USER, content=user_input)
            ]
            response = await provider.complete(messages)
            return response.content

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

    args = parser.parse_args()

    # Import old CLI for backwards compat
    try:
        from ..cli import (
            init_project,
            show_tools,
            show_status,
            show_banner,
            launch_web,
            check_config,
        )

        if args.init:
            init_project()
            return

        if args.status:
            show_status()
            return

        if not args.no_banner:
            show_banner()

        if args.tools:
            if check_config():
                show_tools()
            return

        if args.web:
            if check_config():
                launch_web()
            return

        # Run new async app
        asyncio.run(run_app())

    except ImportError:
        # New-style startup
        asyncio.run(run_app())


if __name__ == "__main__":
    main()
