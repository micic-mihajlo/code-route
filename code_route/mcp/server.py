"""
MCP Server implementation for Code Route.

Provides a Model Context Protocol server that exposes
Code Route tools for use with Claude Desktop and other
MCP-compatible clients.

The server uses stdio transport for communication.
"""

import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TextIO, TYPE_CHECKING
from pathlib import Path

from .handlers import ToolHandler, ResourceHandler, PromptHandler

if TYPE_CHECKING:
    from ..tools.base import BaseTool


# MCP Protocol Constants
JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"


@dataclass
class ServerInfo:
    """MCP server information."""
    name: str = "code-route"
    version: str = "0.2.0"


@dataclass
class ServerCapabilities:
    """MCP server capabilities."""
    tools: bool = True
    resources: bool = True
    prompts: bool = True
    logging: bool = False


class MCPServer:
    """
    Model Context Protocol server for Code Route.

    Exposes tools, resources, and prompts via the MCP
    protocol using stdio transport.

    Usage:
        server = MCPServer()
        server.register_tools(my_tools)
        await server.run()

    Or use the convenience function:
        await run_server(tools=my_tools)
    """

    def __init__(
        self,
        name: str = "code-route",
        version: str = "0.2.0",
        base_path: Optional[Path] = None,
    ):
        """
        Initialize MCP server.

        Args:
            name: Server name
            version: Server version
            base_path: Base path for file resources
        """
        self.info = ServerInfo(name=name, version=version)
        self.capabilities = ServerCapabilities()

        # Handlers
        self.tool_handler = ToolHandler()
        self.resource_handler = ResourceHandler(base_path=base_path)
        self.prompt_handler = PromptHandler()

        # IO
        self._stdin: TextIO = sys.stdin
        self._stdout: TextIO = sys.stdout
        self._running = False

        # Request ID tracking
        self._request_id = 0

    def register_tool(self, tool: "BaseTool") -> None:
        """Register a tool."""
        self.tool_handler.register_tool(tool)

    def register_tools(self, tools: List["BaseTool"]) -> None:
        """Register multiple tools."""
        self.tool_handler.register_tools(tools)

    def _send_message(self, message: Dict[str, Any]) -> None:
        """Send a JSON-RPC message."""
        content = json.dumps(message)
        # MCP uses Content-Length header like LSP
        header = f"Content-Length: {len(content)}\r\n\r\n"
        self._stdout.write(header)
        self._stdout.write(content)
        self._stdout.flush()

    def _send_response(
        self,
        request_id: Any,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send a JSON-RPC response."""
        response: Dict[str, Any] = {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
        }

        if error:
            response["error"] = error
        else:
            response["result"] = result or {}

        self._send_message(response)

    def _send_notification(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send a JSON-RPC notification."""
        notification = {
            "jsonrpc": JSONRPC_VERSION,
            "method": method,
        }
        if params:
            notification["params"] = params

        self._send_message(notification)

    async def _read_message(self) -> Optional[Dict[str, Any]]:
        """Read a JSON-RPC message from stdin."""
        try:
            # Read header
            headers: Dict[str, str] = {}
            while True:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, self._stdin.readline
                )
                if not line:
                    return None

                line = line.strip()
                if not line:
                    break

                if ": " in line:
                    key, value = line.split(": ", 1)
                    headers[key] = value

            # Get content length
            content_length = int(headers.get("Content-Length", 0))
            if content_length == 0:
                return None

            # Read content
            content = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._stdin.read(content_length)
            )

            return json.loads(content)

        except Exception:
            return None

    async def _handle_request(self, request: Dict[str, Any]) -> None:
        """Handle an incoming request."""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        # Dispatch to handler
        handler = getattr(self, f"_handle_{method.replace('/', '_')}", None)

        if handler:
            try:
                result = await handler(params)
                if request_id is not None:
                    self._send_response(request_id, result=result)
            except Exception as e:
                if request_id is not None:
                    self._send_response(
                        request_id,
                        error={
                            "code": -32603,
                            "message": str(e),
                        }
                    )
        else:
            if request_id is not None:
                self._send_response(
                    request_id,
                    error={
                        "code": -32601,
                        "message": f"Method not found: {method}",
                    }
                )

    # === MCP Request Handlers ===

    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request."""
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {} if self.capabilities.tools else None,
                "resources": {} if self.capabilities.resources else None,
                "prompts": {} if self.capabilities.prompts else None,
            },
            "serverInfo": {
                "name": self.info.name,
                "version": self.info.version,
            },
        }

    async def _handle_initialized(self, params: Dict[str, Any]) -> None:
        """Handle initialized notification."""
        pass  # Client is ready

    async def _handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/list request."""
        return {
            "tools": self.tool_handler.list_tools(),
        }

    async def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request."""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        return await self.tool_handler.call_tool(name, arguments)

    async def _handle_resources_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/list request."""
        return {
            "resources": self.resource_handler.list_resources(),
        }

    async def _handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/read request."""
        uri = params.get("uri", "")
        return await self.resource_handler.read_resource(uri)

    async def _handle_prompts_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle prompts/list request."""
        return {
            "prompts": self.prompt_handler.list_prompts(),
        }

    async def _handle_prompts_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle prompts/get request."""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        return await self.prompt_handler.get_prompt(name, arguments)

    async def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ping request."""
        return {}

    async def run(self) -> None:
        """
        Run the MCP server.

        Reads from stdin and writes to stdout in JSON-RPC format.
        """
        self._running = True

        try:
            while self._running:
                message = await self._read_message()
                if message is None:
                    break

                await self._handle_request(message)

        except KeyboardInterrupt:
            pass
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop the server."""
        self._running = False


def create_server(
    tools: Optional[List["BaseTool"]] = None,
    name: str = "code-route",
    version: str = "0.2.0",
    base_path: Optional[Path] = None,
) -> MCPServer:
    """
    Create an MCP server with tools.

    Args:
        tools: Tools to register
        name: Server name
        version: Server version
        base_path: Base path for file resources

    Returns:
        Configured MCPServer
    """
    server = MCPServer(name=name, version=version, base_path=base_path)

    if tools:
        server.register_tools(tools)

    return server


async def run_server(
    tools: Optional[List["BaseTool"]] = None,
    name: str = "code-route",
    version: str = "0.2.0",
    base_path: Optional[Path] = None,
) -> None:
    """
    Create and run an MCP server.

    Args:
        tools: Tools to register
        name: Server name
        version: Server version
        base_path: Base path for file resources
    """
    server = create_server(
        tools=tools,
        name=name,
        version=version,
        base_path=base_path,
    )
    await server.run()


def main():
    """CLI entry point for MCP server."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Code Route MCP Server",
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        help="Base path for file resources",
    )
    parser.add_argument(
        "--name",
        default="code-route",
        help="Server name",
    )
    parser.add_argument(
        "--version",
        default="0.2.0",
        help="Server version",
    )

    args = parser.parse_args()

    # Load default tools
    try:
        from ..tools.base import BaseTool
        from ..tools import get_all_tools

        tools = get_all_tools()
    except ImportError:
        tools = []

    asyncio.run(run_server(
        tools=tools,
        name=args.name,
        version=args.version,
        base_path=args.base_path,
    ))


if __name__ == "__main__":
    main()
