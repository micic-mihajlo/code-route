"""
Code Route MCP Server - Model Context Protocol support.

Exposes Code Route tools via MCP for integration with
Claude Desktop and other MCP-compatible clients.
"""

from .server import MCPServer, create_server, run_server
from .handlers import ToolHandler, ResourceHandler

__all__ = [
    "MCPServer",
    "create_server",
    "run_server",
    "ToolHandler",
    "ResourceHandler",
]
