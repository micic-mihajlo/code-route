"""Shared types and data structures for Code Route."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum


class MessageRole(str, Enum):
    """Message roles in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class Message:
    """A message in a conversation."""
    role: MessageRole
    content: Union[str, List[Dict[str, Any]]]  # str or content blocks for multimodal
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None  # For tool result messages
    name: Optional[str] = None  # Tool name for tool results

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API calls."""
        d = {"role": self.role.value, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments}
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class Usage:
    """Token usage information."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass
class ToolResult:
    """Result from tool execution."""
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    artifacts: List[Dict[str, Any]] = field(default_factory=list)  # Files created, etc.

    @classmethod
    def ok(cls, output: str, metadata: Optional[Dict[str, Any]] = None) -> "ToolResult":
        """Create a successful result."""
        return cls(success=True, output=output, metadata=metadata)

    @classmethod
    def err(cls, error: str, output: str = "") -> "ToolResult":
        """Create an error result."""
        return cls(success=False, output=output, error=error)


@dataclass
class CompletionResponse:
    """Response from an LLM completion call."""
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    usage: Usage = field(default_factory=Usage)
    finish_reason: str = "stop"
    model: Optional[str] = None

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return bool(self.tool_calls)


@dataclass
class ToolSchema:
    """Schema for a tool, used for LLM function calling."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI function format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

    def to_anthropic_format(self) -> Dict[str, Any]:
        """Convert to Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


@dataclass
class AgentTask:
    """A task for an agent to execute."""
    id: str
    description: str
    context: Dict[str, Any] = field(default_factory=dict)
    parent_task_id: Optional[str] = None
    agent_hint: Optional[str] = None  # Suggested agent type


@dataclass
class AgentResult:
    """Result from agent task execution."""
    task_id: str
    success: bool
    output: Any
    error: Optional[str] = None
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    subtasks: List["AgentResult"] = field(default_factory=list)
