"""Base tool classes for Code Route's tool system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Union
import asyncio
import functools
import inspect


@dataclass
class ToolResult:
    """
    Result from tool execution.

    Provides structured output with success/failure indication,
    optional metadata, and artifact tracking.
    """
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    artifacts: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def ok(cls, output: str, metadata: Optional[Dict[str, Any]] = None, artifacts: Optional[List[Dict]] = None) -> "ToolResult":
        """Create a successful result."""
        return cls(success=True, output=output, metadata=metadata, artifacts=artifacts or [])

    @classmethod
    def err(cls, error: str, output: str = "") -> "ToolResult":
        """Create an error result."""
        return cls(success=False, output=output, error=error)

    def __str__(self) -> str:
        """String representation for backwards compatibility."""
        if self.error:
            return f"Error: {self.error}\n{self.output}" if self.output else f"Error: {self.error}"
        return self.output


class BaseTool(ABC):
    """
    Abstract base class for all Code Route tools.

    Tools can be either synchronous or asynchronous. The framework
    automatically handles both through the execute_async() method.

    Example synchronous tool:
        class MyTool(BaseTool):
            @property
            def name(self) -> str:
                return "mytool"

            @property
            def description(self) -> str:
                return "Does something useful"

            @property
            def input_schema(self) -> Dict:
                return {
                    "type": "object",
                    "properties": {
                        "param": {"type": "string", "description": "A parameter"}
                    },
                    "required": ["param"]
                }

            def execute(self, **kwargs) -> str:
                return f"Result: {kwargs.get('param')}"

    Example async tool:
        class MyAsyncTool(BaseTool):
            # ... same properties ...

            async def execute(self, **kwargs) -> ToolResult:
                result = await some_async_operation()
                return ToolResult.ok(result)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Tool name that matches the regex ^[a-zA-Z0-9_-]{1,64}$

        This is used as the function name in LLM tool calling.
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Detailed description of what the tool does.

        This is shown to the LLM to help it decide when to use the tool.
        Be specific about capabilities, inputs, and outputs.
        """
        pass

    @property
    @abstractmethod
    def input_schema(self) -> Dict:
        """
        JSON Schema defining the expected parameters.

        Format:
        {
            "type": "object",
            "properties": {
                "param_name": {
                    "type": "string",
                    "description": "What this parameter does"
                }
            },
            "required": ["param_name"]
        }
        """
        pass

    @property
    def streaming(self) -> bool:
        """
        Whether this tool supports streaming output.

        Override to return True and implement stream() for streaming tools.
        """
        return False

    @property
    def timeout(self) -> Optional[float]:
        """
        Optional timeout in seconds for tool execution.

        Override to set a custom timeout. None means no timeout.
        """
        return None

    @abstractmethod
    def execute(self, **kwargs) -> Union[str, "ToolResult"]:
        """
        Execute the tool with given parameters.

        Can be sync or async. Return either:
        - str: Simple string result (backwards compatible)
        - ToolResult: Structured result with metadata

        For async execution, define as:
            async def execute(self, **kwargs) -> ToolResult:
        """
        pass

    async def execute_async(self, **kwargs) -> ToolResult:
        """
        Execute the tool asynchronously.

        This is the primary entry point used by the framework.
        Automatically handles both sync and async execute() methods.
        """
        try:
            if asyncio.iscoroutinefunction(self.execute):
                result = await self.execute(**kwargs)
            else:
                # Run sync method in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    functools.partial(self.execute, **kwargs)
                )

            # Normalize result to ToolResult
            if isinstance(result, ToolResult):
                return result
            elif isinstance(result, str):
                # Check for error prefix (backwards compat)
                if result.startswith("Error:"):
                    return ToolResult.err(result[6:].strip())
                return ToolResult.ok(result)
            else:
                return ToolResult.ok(str(result))

        except Exception as e:
            return ToolResult.err(str(e))

    async def stream(self, **kwargs) -> AsyncIterator[str]:
        """
        Stream output from the tool.

        Override this method for tools that produce streaming output.
        Default implementation just yields the full result.
        """
        result = await self.execute_async(**kwargs)
        yield result.output

    def validate_input(self, **kwargs) -> Optional[Dict[str, str]]:
        """
        Validate input parameters against the schema.

        Returns None if valid, or a dict of {param: error_message} if invalid.
        Override for custom validation logic.
        """
        schema = self.input_schema
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        errors = {}

        # Check required parameters
        for param in required:
            if param not in kwargs or kwargs[param] is None:
                errors[param] = f"Required parameter '{param}' is missing"

        # Basic type checking
        for param, value in kwargs.items():
            if param in properties and value is not None:
                expected_type = properties[param].get("type")
                if expected_type:
                    if not self._check_type(value, expected_type):
                        errors[param] = f"Expected {expected_type}, got {type(value).__name__}"

        return errors if errors else None

    def _check_type(self, value: Any, expected: str) -> bool:
        """Check if value matches expected JSON Schema type."""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected_types = type_map.get(expected)
        if expected_types is None:
            return True  # Unknown type, allow
        return isinstance(value, expected_types)

    def to_schema(self) -> Dict[str, Any]:
        """
        Convert tool to OpenAI function calling schema.

        Returns a dict suitable for the 'tools' parameter in API calls.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            }
        }

    def to_anthropic_schema(self) -> Dict[str, Any]:
        """Convert tool to Anthropic tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class LegacyToolWrapper(BaseTool):
    """
    Wrapper to adapt legacy synchronous tools to the async interface.

    This is used internally to support existing tools during migration.
    """

    def __init__(self, tool_instance: BaseTool):
        self._wrapped = tool_instance

    @property
    def name(self) -> str:
        return self._wrapped.name

    @property
    def description(self) -> str:
        return self._wrapped.description

    @property
    def input_schema(self) -> Dict:
        return self._wrapped.input_schema

    def execute(self, **kwargs) -> str:
        """Call wrapped tool's execute method."""
        return self._wrapped.execute(**kwargs)


def is_async_tool(tool: BaseTool) -> bool:
    """Check if a tool has an async execute method."""
    return asyncio.iscoroutinefunction(tool.execute)
