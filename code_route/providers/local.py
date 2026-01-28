"""Local LLM provider for LM Studio, Ollama, and other local models."""

import json
from typing import Any, AsyncIterator, Dict, List, Optional

from ..core.types import CompletionResponse, Message, MessageRole, ToolCall, ToolSchema, Usage
from ..core.exceptions import ProviderError
from .base import BaseProvider, ProviderCapabilities, ProviderConfig

try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class LocalProvider(BaseProvider):
    """
    Local LLM provider for self-hosted models.

    Supports:
    - LM Studio (OpenAI-compatible API)
    - Ollama (with OpenAI compatibility layer)
    - vLLM
    - Text Generation WebUI
    - Any OpenAI-compatible local server
    """

    DEFAULT_BASE_URL = "http://localhost:1234/v1"  # LM Studio default
    OLLAMA_BASE_URL = "http://localhost:11434/v1"  # Ollama with OpenAI compat

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if not HAS_OPENAI:
            raise ImportError("openai package required: pip install openai")

        base_url = config.base_url or self.DEFAULT_BASE_URL

        self._client = AsyncOpenAI(
            api_key=config.api_key or "not-needed",  # Local servers often don't need API key
            base_url=base_url,
            timeout=config.timeout or 300.0,  # Local models can be slow
        )
        self._model = config.model or "local-model"
        self._base_url = base_url

    @property
    def name(self) -> str:
        return "local"

    @property
    def capabilities(self) -> ProviderCapabilities:
        # Conservative defaults for local models
        return ProviderCapabilities(
            supports_tools=True,  # Most recent local models support this
            supports_vision=False,  # Depends on model
            supports_streaming=True,
            supports_system_messages=True,
            max_tokens=4096,
            context_window=32000,
        )

    def _prepare_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert messages to OpenAI-compatible format."""
        converted = []

        for msg in messages:
            local_msg: Dict[str, Any] = {
                "role": msg.role.value,
                "content": msg.content,
            }

            # Handle tool results
            if msg.role == MessageRole.TOOL:
                local_msg["tool_call_id"] = msg.tool_call_id
                if msg.name:
                    local_msg["name"] = msg.name

            # Handle assistant messages with tool calls
            if msg.tool_calls:
                local_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else tc.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ]

            converted.append(local_msg)

        return converted

    def _parse_tool_calls(self, tool_calls: Optional[List[Any]]) -> List[ToolCall]:
        """Extract tool calls from response."""
        if not tool_calls:
            return []

        parsed = []
        for tc in tool_calls:
            try:
                arguments = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, AttributeError):
                arguments = tc.function.arguments if hasattr(tc, 'function') else {}

            parsed.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=arguments,
            ))

        return parsed

    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSchema]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
    ) -> CompletionResponse:
        """Get a completion from the local model."""
        local_messages = self._prepare_messages(messages)
        local_tools = self._prepare_tools(tools)

        try:
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "messages": local_messages,
                "max_tokens": max_tokens or self.config.max_tokens,
                "temperature": temperature if temperature is not None else self.config.temperature,
            }

            if local_tools:
                kwargs["tools"] = local_tools

            if stop:
                kwargs["stop"] = stop

            response = await self._client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            return CompletionResponse(
                content=choice.message.content or "",
                tool_calls=self._parse_tool_calls(choice.message.tool_calls) or None,
                usage=Usage(
                    prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                    completion_tokens=response.usage.completion_tokens if response.usage else 0,
                    total_tokens=response.usage.total_tokens if response.usage else 0,
                ),
                finish_reason=choice.finish_reason or "stop",
                model=response.model,
            )

        except Exception as e:
            raise ProviderError(
                message=f"Local model error: {e}",
                provider=self.name,
                retryable=False,
                details={"base_url": self._base_url, "model": self._model}
            )

    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSchema]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
    ) -> AsyncIterator[str]:
        """Stream a completion from the local model."""
        local_messages = self._prepare_messages(messages)
        local_tools = self._prepare_tools(tools)

        try:
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "messages": local_messages,
                "max_tokens": max_tokens or self.config.max_tokens,
                "temperature": temperature if temperature is not None else self.config.temperature,
                "stream": True,
            }

            if local_tools:
                kwargs["tools"] = local_tools

            if stop:
                kwargs["stop"] = stop

            stream = await self._client.chat.completions.create(**kwargs)

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            raise ProviderError(
                message=f"Local model streaming error: {e}",
                provider=self.name,
                details={"base_url": self._base_url, "model": self._model}
            )

    async def health_check(self) -> bool:
        """Check if local server is running."""
        try:
            # Try to list models - works on most local servers
            await self._client.models.list()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Clean up the client."""
        if self._client:
            await self._client.close()
