"""
Keyboard bindings and input handling for Code Route CLI.

Provides vim-like navigation, command shortcuts,
and async input processing.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Union
import sys

# Try to import platform-specific input handling
try:
    if sys.platform == "win32":
        import msvcrt
    else:
        import termios
        import tty
except ImportError:
    pass


class KeyCode(Enum):
    """Common key codes."""
    ENTER = auto()
    ESCAPE = auto()
    BACKSPACE = auto()
    DELETE = auto()
    TAB = auto()
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    HOME = auto()
    END = auto()
    PAGE_UP = auto()
    PAGE_DOWN = auto()
    CTRL_C = auto()
    CTRL_D = auto()
    CTRL_R = auto()
    CTRL_L = auto()
    CTRL_Z = auto()


@dataclass
class KeyEvent:
    """A keyboard event."""
    char: Optional[str] = None
    key: Optional[KeyCode] = None
    ctrl: bool = False
    alt: bool = False
    shift: bool = False

    @property
    def is_printable(self) -> bool:
        """Check if this is a printable character."""
        return self.char is not None and len(self.char) == 1 and self.char.isprintable()

    def __str__(self) -> str:
        parts = []
        if self.ctrl:
            parts.append("Ctrl")
        if self.alt:
            parts.append("Alt")
        if self.shift:
            parts.append("Shift")

        if self.key:
            parts.append(self.key.name)
        elif self.char:
            parts.append(self.char)

        return "+".join(parts) if parts else "Unknown"


# Type for key handlers
KeyHandler = Union[
    Callable[[], None],
    Callable[[], Coroutine[Any, Any, None]],
    Callable[[KeyEvent], None],
    Callable[[KeyEvent], Coroutine[Any, Any, None]],
]


@dataclass
class KeyBinding:
    """A keyboard binding configuration."""
    description: str
    handler: KeyHandler
    key: Optional[KeyCode] = None
    char: Optional[str] = None
    ctrl: bool = False
    alt: bool = False
    enabled: bool = True

    def matches(self, event: KeyEvent) -> bool:
        """Check if this binding matches an event."""
        if not self.enabled:
            return False

        # Check modifiers
        if self.ctrl != event.ctrl:
            return False
        if self.alt != event.alt:
            return False

        # Check key or char
        if self.key is not None:
            return event.key == self.key
        if self.char is not None:
            return event.char == self.char

        return False


class KeyBindings:
    """
    Manage keyboard bindings.

    Supports vim-like navigation and custom shortcuts.
    Bindings can be added, removed, and enabled/disabled.

    Usage:
        bindings = KeyBindings()

        @bindings.add("j")
        def scroll_down():
            print("Scrolling down")

        @bindings.add(ctrl=True, char="c")
        async def cancel():
            print("Cancelled")
    """

    def __init__(self):
        self._bindings: List[KeyBinding] = []
        self._default_handler: Optional[KeyHandler] = None

    def add(
        self,
        char: Optional[str] = None,
        key: Optional[KeyCode] = None,
        ctrl: bool = False,
        alt: bool = False,
        description: str = "",
    ) -> Callable[[KeyHandler], KeyHandler]:
        """
        Decorator to add a key binding.

        Args:
            char: Character to bind to
            key: Key code to bind to
            ctrl: Require Ctrl modifier
            alt: Require Alt modifier
            description: Description of the action

        Returns:
            Decorator function
        """
        def decorator(handler: KeyHandler) -> KeyHandler:
            self._bindings.append(KeyBinding(
                description=description or handler.__name__,
                handler=handler,
                key=key,
                char=char,
                ctrl=ctrl,
                alt=alt,
            ))
            return handler
        return decorator

    def bind(
        self,
        handler: KeyHandler,
        char: Optional[str] = None,
        key: Optional[KeyCode] = None,
        ctrl: bool = False,
        alt: bool = False,
        description: str = "",
    ) -> None:
        """Add a binding directly (non-decorator)."""
        self._bindings.append(KeyBinding(
            description=description,
            handler=handler,
            key=key,
            char=char,
            ctrl=ctrl,
            alt=alt,
        ))

    def unbind(self, char: Optional[str] = None, key: Optional[KeyCode] = None) -> None:
        """Remove a binding."""
        self._bindings = [
            b for b in self._bindings
            if not (b.char == char and b.key == key)
        ]

    def set_default(self, handler: KeyHandler) -> None:
        """Set default handler for unbound keys."""
        self._default_handler = handler

    def enable(self, char: Optional[str] = None, key: Optional[KeyCode] = None) -> None:
        """Enable a binding."""
        for binding in self._bindings:
            if binding.char == char and binding.key == key:
                binding.enabled = True

    def disable(self, char: Optional[str] = None, key: Optional[KeyCode] = None) -> None:
        """Disable a binding."""
        for binding in self._bindings:
            if binding.char == char and binding.key == key:
                binding.enabled = False

    def get_handler(self, event: KeyEvent) -> Optional[KeyHandler]:
        """Get the handler for an event."""
        for binding in self._bindings:
            if binding.matches(event):
                return binding.handler
        return self._default_handler

    async def dispatch(self, event: KeyEvent) -> bool:
        """
        Dispatch an event to its handler.

        Args:
            event: The key event

        Returns:
            True if a handler was called
        """
        handler = self.get_handler(event)
        if handler is None:
            return False

        # Call handler (may be sync or async)
        try:
            result = handler(event) if _accepts_event(handler) else handler()
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            # Let errors propagate but don't crash on handler errors
            raise

        return True

    def get_help(self) -> Dict[str, str]:
        """Get help text for all bindings."""
        help_items = {}
        for binding in self._bindings:
            if not binding.enabled:
                continue

            # Build key string
            parts = []
            if binding.ctrl:
                parts.append("Ctrl")
            if binding.alt:
                parts.append("Alt")
            if binding.key:
                parts.append(binding.key.name)
            elif binding.char:
                parts.append(binding.char)

            key_str = "+".join(parts)
            help_items[key_str] = binding.description

        return help_items


def _accepts_event(handler: KeyHandler) -> bool:
    """Check if handler accepts a KeyEvent parameter."""
    import inspect
    sig = inspect.signature(handler)
    return len(sig.parameters) > 0


class InputHandler:
    """
    Async input handler for terminal.

    Handles raw keyboard input with support for
    special keys, modifiers, and escape sequences.

    Usage:
        handler = InputHandler(bindings)

        async for event in handler.read():
            print(f"Key: {event}")
    """

    def __init__(
        self,
        bindings: Optional[KeyBindings] = None,
        echo: bool = True,
    ):
        self.bindings = bindings or KeyBindings()
        self.echo = echo
        self._running = False
        self._buffer: List[str] = []

    async def read_key(self) -> Optional[KeyEvent]:
        """
        Read a single key event.

        Returns:
            KeyEvent or None if no input
        """
        if sys.platform == "win32":
            return await self._read_key_windows()
        else:
            return await self._read_key_unix()

    async def _read_key_windows(self) -> Optional[KeyEvent]:
        """Read key on Windows."""
        if not msvcrt.kbhit():
            await asyncio.sleep(0.01)  # Small delay to prevent busy loop
            return None

        char = msvcrt.getwch()

        # Handle special keys
        if char == '\x00' or char == '\xe0':
            # Extended key
            char2 = msvcrt.getwch()
            return self._parse_windows_extended(char2)

        # Ctrl+key combinations
        if ord(char) < 32:
            return self._parse_control_char(char)

        return KeyEvent(char=char)

    async def _read_key_unix(self) -> Optional[KeyEvent]:
        """Read key on Unix/Linux/Mac."""
        import select

        # Check if input is available
        if not select.select([sys.stdin], [], [], 0.01)[0]:
            return None

        char = sys.stdin.read(1)
        if not char:
            return None

        # Handle escape sequences
        if char == '\x1b':
            return await self._parse_escape_sequence()

        # Ctrl+key combinations
        if ord(char) < 32:
            return self._parse_control_char(char)

        return KeyEvent(char=char)

    async def _parse_escape_sequence(self) -> KeyEvent:
        """Parse an escape sequence."""
        import select

        # Read next chars if available
        chars = ['\x1b']
        while select.select([sys.stdin], [], [], 0.01)[0]:
            char = sys.stdin.read(1)
            if char:
                chars.append(char)
            else:
                break

        seq = ''.join(chars)

        # Common sequences
        sequences = {
            '\x1b[A': KeyEvent(key=KeyCode.UP),
            '\x1b[B': KeyEvent(key=KeyCode.DOWN),
            '\x1b[C': KeyEvent(key=KeyCode.RIGHT),
            '\x1b[D': KeyEvent(key=KeyCode.LEFT),
            '\x1b[H': KeyEvent(key=KeyCode.HOME),
            '\x1b[F': KeyEvent(key=KeyCode.END),
            '\x1b[5~': KeyEvent(key=KeyCode.PAGE_UP),
            '\x1b[6~': KeyEvent(key=KeyCode.PAGE_DOWN),
            '\x1b[3~': KeyEvent(key=KeyCode.DELETE),
        }

        if seq in sequences:
            return sequences[seq]

        # Just escape
        if len(chars) == 1:
            return KeyEvent(key=KeyCode.ESCAPE)

        # Unknown sequence - return as escape
        return KeyEvent(key=KeyCode.ESCAPE)

    def _parse_windows_extended(self, char: str) -> KeyEvent:
        """Parse Windows extended key."""
        code = ord(char)
        mapping = {
            72: KeyCode.UP,
            80: KeyCode.DOWN,
            75: KeyCode.LEFT,
            77: KeyCode.RIGHT,
            71: KeyCode.HOME,
            79: KeyCode.END,
            73: KeyCode.PAGE_UP,
            81: KeyCode.PAGE_DOWN,
            83: KeyCode.DELETE,
        }
        key = mapping.get(code)
        if key:
            return KeyEvent(key=key)
        return KeyEvent(char=char)

    def _parse_control_char(self, char: str) -> KeyEvent:
        """Parse a control character."""
        code = ord(char)
        mapping = {
            3: KeyEvent(key=KeyCode.CTRL_C, ctrl=True),
            4: KeyEvent(key=KeyCode.CTRL_D, ctrl=True),
            18: KeyEvent(key=KeyCode.CTRL_R, ctrl=True),
            12: KeyEvent(key=KeyCode.CTRL_L, ctrl=True),
            26: KeyEvent(key=KeyCode.CTRL_Z, ctrl=True),
            13: KeyEvent(key=KeyCode.ENTER),
            10: KeyEvent(key=KeyCode.ENTER),
            9: KeyEvent(key=KeyCode.TAB),
            127: KeyEvent(key=KeyCode.BACKSPACE),
            8: KeyEvent(key=KeyCode.BACKSPACE),
        }
        return mapping.get(code, KeyEvent(char=char, ctrl=True))

    async def read(self):
        """
        Async generator for reading key events.

        Yields:
            KeyEvent for each key press
        """
        self._running = True

        try:
            while self._running:
                event = await self.read_key()
                if event:
                    yield event
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop reading input."""
        self._running = False

    async def run(self) -> None:
        """
        Run the input loop, dispatching to bindings.

        Continues until stopped or Ctrl+C.
        """
        async for event in self.read():
            try:
                await self.bindings.dispatch(event)
            except KeyboardInterrupt:
                break


class LineEditor:
    """
    Simple line editor with history.

    Supports editing, history navigation,
    and common shortcuts.
    """

    def __init__(
        self,
        history_size: int = 100,
        prompt: str = "> ",
    ):
        self.history: List[str] = []
        self.history_size = history_size
        self.prompt = prompt

        self._line = ""
        self._cursor = 0
        self._history_index = -1

    @property
    def line(self) -> str:
        """Get current line content."""
        return self._line

    @property
    def cursor(self) -> int:
        """Get cursor position."""
        return self._cursor

    def insert(self, char: str) -> None:
        """Insert a character at cursor."""
        self._line = self._line[:self._cursor] + char + self._line[self._cursor:]
        self._cursor += len(char)

    def delete_back(self) -> None:
        """Delete character before cursor."""
        if self._cursor > 0:
            self._line = self._line[:self._cursor - 1] + self._line[self._cursor:]
            self._cursor -= 1

    def delete_forward(self) -> None:
        """Delete character at cursor."""
        if self._cursor < len(self._line):
            self._line = self._line[:self._cursor] + self._line[self._cursor + 1:]

    def move_left(self) -> None:
        """Move cursor left."""
        if self._cursor > 0:
            self._cursor -= 1

    def move_right(self) -> None:
        """Move cursor right."""
        if self._cursor < len(self._line):
            self._cursor += 1

    def move_home(self) -> None:
        """Move cursor to start."""
        self._cursor = 0

    def move_end(self) -> None:
        """Move cursor to end."""
        self._cursor = len(self._line)

    def history_up(self) -> None:
        """Navigate history up."""
        if self._history_index < len(self.history) - 1:
            self._history_index += 1
            self._line = self.history[-(self._history_index + 1)]
            self._cursor = len(self._line)

    def history_down(self) -> None:
        """Navigate history down."""
        if self._history_index > 0:
            self._history_index -= 1
            self._line = self.history[-(self._history_index + 1)]
            self._cursor = len(self._line)
        elif self._history_index == 0:
            self._history_index = -1
            self._line = ""
            self._cursor = 0

    def submit(self) -> str:
        """Submit current line and add to history."""
        line = self._line

        if line.strip():
            self.history.append(line)
            if len(self.history) > self.history_size:
                self.history = self.history[-self.history_size:]

        self._line = ""
        self._cursor = 0
        self._history_index = -1

        return line

    def clear(self) -> None:
        """Clear current line."""
        self._line = ""
        self._cursor = 0
        self._history_index = -1

    def handle_key(self, event: KeyEvent) -> Optional[str]:
        """
        Handle a key event.

        Args:
            event: Key event to handle

        Returns:
            Submitted line if Enter pressed, None otherwise
        """
        if event.key == KeyCode.ENTER:
            return self.submit()
        elif event.key == KeyCode.BACKSPACE:
            self.delete_back()
        elif event.key == KeyCode.DELETE:
            self.delete_forward()
        elif event.key == KeyCode.LEFT:
            self.move_left()
        elif event.key == KeyCode.RIGHT:
            self.move_right()
        elif event.key == KeyCode.HOME:
            self.move_home()
        elif event.key == KeyCode.END:
            self.move_end()
        elif event.key == KeyCode.UP:
            self.history_up()
        elif event.key == KeyCode.DOWN:
            self.history_down()
        elif event.is_printable:
            self.insert(event.char)

        return None


def create_default_bindings() -> KeyBindings:
    """
    Create default vim-like key bindings.

    Returns:
        KeyBindings with common shortcuts
    """
    bindings = KeyBindings()

    # These are placeholders - actual handlers are set by the app
    @bindings.add("j", description="Scroll down")
    def scroll_down():
        pass

    @bindings.add("k", description="Scroll up")
    def scroll_up():
        pass

    @bindings.add("g", description="Go to top")
    def go_top():
        pass

    @bindings.add("G", description="Go to bottom")
    def go_bottom():
        pass

    @bindings.add("q", description="Quit")
    def quit_app():
        pass

    @bindings.add("?", description="Toggle help")
    def toggle_help():
        pass

    @bindings.add(ctrl=True, char="c", description="Cancel/Interrupt")
    def cancel():
        pass

    @bindings.add(ctrl=True, char="r", description="Refresh")
    def refresh():
        pass

    @bindings.add(ctrl=True, char="l", description="Clear screen")
    def clear_screen():
        pass

    return bindings
