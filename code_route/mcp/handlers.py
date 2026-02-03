"""
MCP request handlers for Code Route.

Provides handlers for tool execution, resource access,
and prompt management in the MCP protocol.
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from ..tools.base import BaseTool


@dataclass
class ToolDefinition:
    """MCP tool definition."""
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class ResourceDefinition:
    """MCP resource definition."""
    uri: str
    name: str
    description: str
    mime_type: str = "text/plain"


@dataclass
class PromptDefinition:
    """MCP prompt definition."""
    name: str
    description: str
    arguments: List[Dict[str, Any]] = field(default_factory=list)


class ToolHandler:
    """
    Handles tool-related MCP requests.

    Manages tool registration, discovery, and execution
    for MCP clients.

    Usage:
        handler = ToolHandler()
        handler.register_tool(my_tool)

        # List tools for MCP
        tools = handler.list_tools()

        # Execute a tool
        result = await handler.call_tool("file_read", {"path": "/foo/bar"})
    """

    def __init__(self):
        self._tools: Dict[str, "BaseTool"] = {}
        self._tool_definitions: Dict[str, ToolDefinition] = {}

    def register_tool(self, tool: "BaseTool") -> None:
        """
        Register a tool for MCP access.

        Args:
            tool: Tool instance to register
        """
        name = tool.name
        self._tools[name] = tool
        self._tool_definitions[name] = ToolDefinition(
            name=name,
            description=tool.description,
            input_schema=tool.input_schema,
        )

    def register_tools(self, tools: List["BaseTool"]) -> None:
        """Register multiple tools."""
        for tool in tools:
            self.register_tool(tool)

    def unregister_tool(self, name: str) -> bool:
        """Unregister a tool by name."""
        if name in self._tools:
            del self._tools[name]
            del self._tool_definitions[name]
            return True
        return False

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List all registered tools in MCP format.

        Returns:
            List of tool definitions
        """
        return [
            {
                "name": defn.name,
                "description": defn.description,
                "inputSchema": defn.input_schema,
            }
            for defn in self._tool_definitions.values()
        ]

    async def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a tool and return MCP-formatted result.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            MCP tool result with content
        """
        if name not in self._tools:
            return {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": f"Unknown tool: {name}",
                    }
                ],
            }

        tool = self._tools[name]
        arguments = arguments or {}

        try:
            # Execute tool (handles both sync and async)
            result = await tool.execute_async(**arguments)

            # Format result for MCP
            if result.success:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": result.output,
                        }
                    ],
                }
            else:
                return {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error: {result.error}",
                        }
                    ],
                }

        except Exception as e:
            return {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": f"Tool execution failed: {str(e)}",
                    }
                ],
            }

    def get_tool(self, name: str) -> Optional["BaseTool"]:
        """Get a tool by name."""
        return self._tools.get(name)


class ResourceHandler:
    """
    Handles resource-related MCP requests.

    Manages file and data resources that can be
    accessed by MCP clients.

    Usage:
        handler = ResourceHandler(base_path="/my/project")

        # List resources
        resources = handler.list_resources()

        # Read a resource
        content = await handler.read_resource("file:///my/project/README.md")
    """

    def __init__(
        self,
        base_path: Optional[Path] = None,
        allowed_extensions: Optional[List[str]] = None,
    ):
        """
        Initialize resource handler.

        Args:
            base_path: Base path for file resources
            allowed_extensions: File extensions to expose (None = all)
        """
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self.allowed_extensions = allowed_extensions or [
            ".py", ".js", ".ts", ".json", ".yaml", ".yml",
            ".md", ".txt", ".rst", ".toml", ".ini", ".cfg",
            ".html", ".css", ".sql", ".sh", ".bash",
        ]
        self._custom_resources: Dict[str, ResourceDefinition] = {}
        self._resource_handlers: Dict[str, Callable] = {}

    def register_resource(
        self,
        uri: str,
        name: str,
        description: str,
        handler: Callable,
        mime_type: str = "text/plain",
    ) -> None:
        """
        Register a custom resource.

        Args:
            uri: Resource URI
            name: Display name
            description: Resource description
            handler: Async function to get resource content
            mime_type: Content MIME type
        """
        self._custom_resources[uri] = ResourceDefinition(
            uri=uri,
            name=name,
            description=description,
            mime_type=mime_type,
        )
        self._resource_handlers[uri] = handler

    def list_resources(self) -> List[Dict[str, Any]]:
        """
        List available resources.

        Returns:
            List of resource definitions
        """
        resources = []

        # Add custom resources
        for defn in self._custom_resources.values():
            resources.append({
                "uri": defn.uri,
                "name": defn.name,
                "description": defn.description,
                "mimeType": defn.mime_type,
            })

        # Add file resources from base path
        if self.base_path.exists():
            for ext in self.allowed_extensions:
                for file_path in self.base_path.rglob(f"*{ext}"):
                    # Skip hidden files and directories
                    if any(part.startswith(".") for part in file_path.parts):
                        continue

                    rel_path = file_path.relative_to(self.base_path)
                    resources.append({
                        "uri": f"file:///{file_path.as_posix()}",
                        "name": str(rel_path),
                        "description": f"Source file: {rel_path}",
                        "mimeType": self._get_mime_type(ext),
                    })

        return resources

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """
        Read a resource by URI.

        Args:
            uri: Resource URI

        Returns:
            MCP resource content
        """
        # Check custom resources first
        if uri in self._resource_handlers:
            handler = self._resource_handlers[uri]
            try:
                content = await handler() if asyncio.iscoroutinefunction(handler) else handler()
                defn = self._custom_resources[uri]
                return {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": defn.mime_type,
                            "text": content,
                        }
                    ],
                }
            except Exception as e:
                return {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "text/plain",
                            "text": f"Error reading resource: {e}",
                        }
                    ],
                }

        # Handle file:// URIs
        if uri.startswith("file:///"):
            file_path = Path(uri[8:])  # Remove file:///
            return await self._read_file_resource(file_path)

        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/plain",
                    "text": f"Unknown resource: {uri}",
                }
            ],
        }

    async def _read_file_resource(self, file_path: Path) -> Dict[str, Any]:
        """Read a file resource."""
        try:
            # Security check - ensure file is under base path
            resolved = file_path.resolve()
            base_resolved = self.base_path.resolve()

            try:
                resolved.relative_to(base_resolved)
            except ValueError:
                return {
                    "contents": [
                        {
                            "uri": f"file:///{file_path.as_posix()}",
                            "mimeType": "text/plain",
                            "text": "Access denied: path outside base directory",
                        }
                    ],
                }

            if not resolved.exists():
                return {
                    "contents": [
                        {
                            "uri": f"file:///{file_path.as_posix()}",
                            "mimeType": "text/plain",
                            "text": f"File not found: {file_path}",
                        }
                    ],
                }

            content = resolved.read_text(encoding="utf-8")
            mime_type = self._get_mime_type(resolved.suffix)

            return {
                "contents": [
                    {
                        "uri": f"file:///{resolved.as_posix()}",
                        "mimeType": mime_type,
                        "text": content,
                    }
                ],
            }

        except Exception as e:
            return {
                "contents": [
                    {
                        "uri": f"file:///{file_path.as_posix()}",
                        "mimeType": "text/plain",
                        "text": f"Error reading file: {e}",
                    }
                ],
            }

    def _get_mime_type(self, ext: str) -> str:
        """Get MIME type for file extension."""
        mime_types = {
            ".py": "text/x-python",
            ".js": "text/javascript",
            ".ts": "text/typescript",
            ".json": "application/json",
            ".yaml": "text/yaml",
            ".yml": "text/yaml",
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".html": "text/html",
            ".css": "text/css",
            ".sql": "text/x-sql",
            ".sh": "text/x-shellscript",
            ".bash": "text/x-shellscript",
            ".toml": "text/x-toml",
        }
        return mime_types.get(ext, "text/plain")


class PromptHandler:
    """
    Handles prompt-related MCP requests.

    Manages prompt templates that can be used by
    MCP clients to structure interactions.
    """

    def __init__(self):
        self._prompts: Dict[str, PromptDefinition] = {}
        self._prompt_generators: Dict[str, Callable] = {}

    def register_prompt(
        self,
        name: str,
        description: str,
        generator: Callable,
        arguments: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Register a prompt template.

        Args:
            name: Prompt name
            description: Prompt description
            generator: Function to generate prompt messages
            arguments: Argument definitions
        """
        self._prompts[name] = PromptDefinition(
            name=name,
            description=description,
            arguments=arguments or [],
        )
        self._prompt_generators[name] = generator

    def list_prompts(self) -> List[Dict[str, Any]]:
        """List available prompts."""
        return [
            {
                "name": defn.name,
                "description": defn.description,
                "arguments": defn.arguments,
            }
            for defn in self._prompts.values()
        ]

    async def get_prompt(
        self,
        name: str,
        arguments: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Get a prompt with arguments applied.

        Args:
            name: Prompt name
            arguments: Argument values

        Returns:
            MCP prompt response with messages
        """
        if name not in self._prompt_generators:
            return {
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": f"Unknown prompt: {name}",
                        },
                    }
                ],
            }

        generator = self._prompt_generators[name]
        arguments = arguments or {}

        try:
            if asyncio.iscoroutinefunction(generator):
                messages = await generator(**arguments)
            else:
                messages = generator(**arguments)

            return {"messages": messages}

        except Exception as e:
            return {
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": f"Error generating prompt: {e}",
                        },
                    }
                ],
            }
