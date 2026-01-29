"""
Real-time streaming renderer using Rich Live.

Handles token-by-token display with markdown rendering,
code block detection, and smooth updates.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, List, Optional, AsyncIterator
import re

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.spinner import Spinner
from rich.progress import Progress, SpinnerColumn, TextColumn


class StreamState(Enum):
    """Current state of the streaming renderer."""
    IDLE = auto()
    STREAMING = auto()
    CODE_BLOCK = auto()
    PAUSED = auto()
    COMPLETE = auto()


@dataclass
class TokenBuffer:
    """
    Buffer for accumulating streamed tokens.

    Handles partial markdown, code blocks, and
    provides efficient rendering updates.
    """
    content: str = ""
    code_blocks: List[dict] = field(default_factory=list)
    current_code_block: Optional[dict] = None
    _in_code_block: bool = False
    _code_fence_pattern: re.Pattern = field(
        default_factory=lambda: re.compile(r'^```(\w+)?$', re.MULTILINE)
    )

    def append(self, token: str) -> None:
        """Append a token to the buffer."""
        self.content += token
        self._detect_code_blocks()

    def _detect_code_blocks(self) -> None:
        """Detect and track code block boundaries."""
        lines = self.content.split('\n')
        in_block = False
        current_lang = None
        block_start = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('```'):
                if not in_block:
                    # Starting a code block
                    in_block = True
                    lang_match = re.match(r'^```(\w+)?', stripped)
                    current_lang = lang_match.group(1) if lang_match else None
                    block_start = i
                else:
                    # Ending a code block
                    in_block = False
                    self.current_code_block = None

        self._in_code_block = in_block
        if in_block:
            self.current_code_block = {
                "language": current_lang,
                "start_line": block_start,
            }

    @property
    def is_in_code_block(self) -> bool:
        """Check if currently inside a code block."""
        return self._in_code_block

    def clear(self) -> None:
        """Clear the buffer."""
        self.content = ""
        self.code_blocks = []
        self.current_code_block = None
        self._in_code_block = False

    def get_display_content(self) -> str:
        """Get content suitable for display."""
        return self.content

    def __str__(self) -> str:
        return self.content


class StreamingRenderer:
    """
    Real-time streaming renderer using Rich Live.

    Features:
    - Token-by-token display with smooth updates
    - Markdown rendering as content streams
    - Code block syntax highlighting
    - Spinner during generation
    - Pause/resume support

    Usage:
        renderer = StreamingRenderer(console)

        async with renderer.stream() as stream:
            async for token in provider.stream(messages):
                await stream.push(token)
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        refresh_rate: int = 10,
        show_cursor: bool = True,
        panel_title: str = "Assistant",
    ):
        """
        Initialize streaming renderer.

        Args:
            console: Rich console to use
            refresh_rate: Updates per second
            show_cursor: Show blinking cursor during stream
            panel_title: Title for the output panel
        """
        self.console = console or Console()
        self.refresh_rate = refresh_rate
        self.show_cursor = show_cursor
        self.panel_title = panel_title

        self.buffer = TokenBuffer()
        self.state = StreamState.IDLE
        self._live: Optional[Live] = None
        self._on_complete: Optional[Callable[[str], None]] = None

    def _render_content(self) -> Any:
        """Render current buffer content."""
        content = self.buffer.get_display_content()

        if not content:
            # Show simple text indicator (ASCII-safe for Windows)
            return Text("Thinking...", style="cyan italic")

        # Add cursor if streaming
        display_content = content
        if self.state == StreamState.STREAMING and self.show_cursor:
            display_content += " [blink]|[/blink]"

        # Render as markdown
        try:
            rendered = Markdown(display_content)
        except Exception:
            # Fallback to plain text if markdown fails
            rendered = Text(display_content)

        return Panel(
            rendered,
            title=f"[bold cyan]{self.panel_title}[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )

    async def push(self, token: str) -> None:
        """
        Push a token to the stream.

        Args:
            token: Token to append
        """
        if self.state == StreamState.PAUSED:
            return

        self.buffer.append(token)

        if self._live:
            self._live.update(self._render_content())

    async def push_all(self, tokens: AsyncIterator[str]) -> str:
        """
        Push all tokens from an async iterator.

        Args:
            tokens: Async iterator of tokens

        Returns:
            Complete content
        """
        async for token in tokens:
            await self.push(token)
        return self.buffer.content

    def pause(self) -> None:
        """Pause streaming (ignore new tokens)."""
        self.state = StreamState.PAUSED

    def resume(self) -> None:
        """Resume streaming."""
        if self.state == StreamState.PAUSED:
            self.state = StreamState.STREAMING

    def on_complete(self, callback: Callable[[str], None]) -> None:
        """Register completion callback."""
        self._on_complete = callback

    class _StreamContext:
        """Context manager for streaming session."""

        def __init__(self, renderer: "StreamingRenderer"):
            self.renderer = renderer

        async def __aenter__(self) -> "StreamingRenderer":
            self.renderer.buffer.clear()
            self.renderer.state = StreamState.STREAMING

            self.renderer._live = Live(
                self.renderer._render_content(),
                console=self.renderer.console,
                refresh_per_second=self.renderer.refresh_rate,
                transient=False,
            )
            self.renderer._live.__enter__()

            return self.renderer

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            self.renderer.state = StreamState.COMPLETE

            # Final render without cursor
            if self.renderer._live:
                self.renderer._live.update(self.renderer._render_content())
                self.renderer._live.__exit__(exc_type, exc_val, exc_tb)
                self.renderer._live = None

            # Call completion callback
            if self.renderer._on_complete:
                self.renderer._on_complete(self.renderer.buffer.content)

            return False

        async def push(self, token: str) -> None:
            """Push a token."""
            await self.renderer.push(token)

    def stream(self) -> _StreamContext:
        """
        Start a streaming session.

        Usage:
            async with renderer.stream() as stream:
                async for token in tokens:
                    await stream.push(token)
        """
        return self._StreamContext(self)

    async def stream_tokens(self, tokens: AsyncIterator[str]) -> str:
        """
        Convenience method to stream all tokens.

        Args:
            tokens: Async iterator of tokens

        Returns:
            Complete content
        """
        async with self.stream():
            return await self.push_all(tokens)


class ThinkingIndicator:
    """
    Display a thinking/processing indicator.

    Shows a spinner with optional status messages.
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        message: str = "Thinking",
    ):
        self.console = console or Console()
        self.message = message
        self._progress: Optional[Progress] = None
        self._task_id: Optional[int] = None

    def __enter__(self) -> "ThinkingIndicator":
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[cyan]{task.description}[/cyan]"),
            console=self.console,
            transient=True,
        )
        self._progress.__enter__()
        self._task_id = self._progress.add_task(self.message, total=None)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._progress:
            self._progress.__exit__(exc_type, exc_val, exc_tb)
        return False

    def update(self, message: str) -> None:
        """Update the status message."""
        if self._progress and self._task_id is not None:
            self._progress.update(self._task_id, description=message)


class MultiStreamRenderer:
    """
    Render multiple concurrent streams (e.g., parallel agents).

    Displays multiple panels that update independently.
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        refresh_rate: int = 10,
    ):
        self.console = console or Console()
        self.refresh_rate = refresh_rate
        self.streams: dict[str, TokenBuffer] = {}
        self._live: Optional[Live] = None

    def add_stream(self, stream_id: str, title: str = "") -> None:
        """Add a new stream."""
        self.streams[stream_id] = TokenBuffer()

    def remove_stream(self, stream_id: str) -> None:
        """Remove a stream."""
        self.streams.pop(stream_id, None)

    async def push(self, stream_id: str, token: str) -> None:
        """Push a token to a specific stream."""
        if stream_id in self.streams:
            self.streams[stream_id].append(token)
            self._update_display()

    def _render_all(self) -> Group:
        """Render all streams."""
        panels = []
        for stream_id, buffer in self.streams.items():
            content = buffer.content or "[dim]Waiting...[/dim]"
            try:
                rendered = Markdown(content)
            except Exception:
                rendered = Text(content)

            panels.append(Panel(
                rendered,
                title=f"[bold cyan]{stream_id}[/bold cyan]",
                border_style="cyan",
            ))

        return Group(*panels)

    def _update_display(self) -> None:
        """Update the live display."""
        if self._live:
            self._live.update(self._render_all())

    async def __aenter__(self) -> "MultiStreamRenderer":
        self._live = Live(
            self._render_all(),
            console=self.console,
            refresh_per_second=self.refresh_rate,
        )
        self._live.__enter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._live:
            self._live.__exit__(exc_type, exc_val, exc_tb)
            self._live = None
        return False
