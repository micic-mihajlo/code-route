"""
Code Route - A self-improving AI assistant framework with dynamic tool creation.

This package provides a powerful assistant framework that can create and execute
tools dynamically, making it extensible and self-improving.
"""

__version__ = "0.1.0"
__author__ = "Mihajlo Micic"
__email__ = "mihajlo@example.com"

from .config import Config

__all__ = ["Assistant", "Config"]


def __getattr__(name: str):
    """Lazy-load heavy imports so light package imports keep working."""
    if name == "Assistant":
        from .assistant import Assistant

        return Assistant
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
