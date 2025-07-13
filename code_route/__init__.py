"""
Code Route - A self-improving AI assistant framework with dynamic tool creation.

This package provides a powerful assistant framework that can create and execute
tools dynamically, making it extensible and self-improving.
"""

__version__ = "0.1.0"
__author__ = "Mihajlo Micic"
__email__ = "mihajlo@example.com"

from .assistant import Assistant
from .config import Config

__all__ = ["Assistant", "Config"]