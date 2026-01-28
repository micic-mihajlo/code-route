"""
Code Route CLI - Enhanced terminal interface.

Provides streaming TUI with Rich, async event handling,
and vim-like navigation.
"""

from .streaming import StreamingRenderer, TokenBuffer
from .panels import (
    ToolPanel,
    AgentPanel,
    TokenUsagePanel,
    StatusBar,
    ConversationPanel,
)
from .keybindings import KeyBindings, InputHandler
from .app import CodeRouteApp, run_app

__all__ = [
    # Streaming
    "StreamingRenderer",
    "TokenBuffer",
    # Panels
    "ToolPanel",
    "AgentPanel",
    "TokenUsagePanel",
    "StatusBar",
    "ConversationPanel",
    # Input
    "KeyBindings",
    "InputHandler",
    # App
    "CodeRouteApp",
    "run_app",
]
