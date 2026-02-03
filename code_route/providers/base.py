"""Base provider protocol for LLM integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from ..core.types import CompletionResponse, Message, MessageRole, ToolSchema, Usage


@dataclass
class ProviderCapabilities:
    """Capabilities of a provider."""
    supports_tools: bool = True
    supports_vision: bool = False
    supports_streaming: bool = True
    supports_system_messages: bool = True
    max_tokens: int = 8192
    context_window: int = 128000


@dataclass
class ProviderConfig:
    """Configuration for a provider."""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 8192
    timeout: float = 120.0
    extra: Dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    """
    Abstract base class for LLM providers.

    All providers must implement:
    - complete(): Single completion call
    - stream(): Streaming completion
    - name property: Provider identifier
    - capabilities property: What the provider supports
    """

    def __init__(self, config: ProviderConfig):
        self.config = config
        self._client: Any = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Provider capabilities."""
        pass

    @abstractmethod
    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSchema]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
    ) -> CompletionResponse:
        """
        Get a completion from the LLM.

        Args:
            messages: Conversation history
            tools: Available tools for function calling
            temperature: Sampling temperature (overrides config)
            max_tokens: Max tokens to generate (overrides config)
            stop: Stop sequences

        Returns:
            CompletionResponse with content and optional tool calls
        """
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSchema]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
    ) -> AsyncIterator[str]:
        """
        Stream a completion from the LLM.

        Args:
            messages: Conversation history
            tools: Available tools for function calling
            temperature: Sampling temperature (overrides config)
            max_tokens: Max tokens to generate (overrides config)
            stop: Stop sequences

        Yields:
            Text chunks as they arrive
        """
        pass

    def _prepare_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert Message objects to provider-specific format."""
        return [msg.to_dict() for msg in messages]

    def _prepare_tools(self, tools: Optional[List[ToolSchema]]) -> Optional[List[Dict[str, Any]]]:
        """Convert ToolSchema objects to provider-specific format."""
        if not tools:
            return None
        # Default to OpenAI format, subclasses can override
        return [tool.to_openai_format() for tool in tools]

    async def health_check(self) -> bool:
        """Check if the provider is accessible."""
        try:
            # Simple completion test
            response = await self.complete(
                messages=[Message(role=MessageRole.USER, content="Hi")],
                max_tokens=5,
            )
            return bool(response.content)
        except Exception:
            return False

    async def close(self) -> None:
        """Clean up resources."""
        pass

    async def __aenter__(self) -> "BaseProvider":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
