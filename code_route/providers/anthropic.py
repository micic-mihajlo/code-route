"""Anthropic Claude provider implementation."""

import json
from typing import Any, AsyncIterator, Dict, List, Optional

from ..core.types import CompletionResponse, Message, MessageRole, ToolCall, ToolSchema, Usage
from ..core.exceptions import ProviderError, RateLimitError, AuthenticationError
from .base import BaseProvider, ProviderCapabilities, ProviderConfig

try:
    import anthropic
    from anthropic import AsyncAnthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


class AnthropicProvider(BaseProvider):
    """
    Native Anthropic Claude provider.

    Supports Claude 3.5 Sonnet, Claude 3 Opus, Haiku, and future models.
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if not HAS_ANTHROPIC:
            raise ImportError("anthropic package required: pip install anthropic")

        self._client = AsyncAnthropic(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )
        self._model = config.model or self.DEFAULT_MODEL

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_tools=True,
            supports_vision=True,
            supports_streaming=True,
            supports_system_messages=True,
            max_tokens=8192,
            context_window=200000,  # Claude 3.5 Sonnet
        )

    def _prepare_messages(self, messages: List[Message]) -> tuple[Optional[str], List[Dict[str, Any]]]:
        """
        Convert messages to Anthropic format.

        Returns (system_prompt, messages) tuple since Anthropic handles system separately.
        """
        system_prompt = None
        converted = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # Anthropic uses separate system parameter
                system_prompt = msg.content if isinstance(msg.content, str) else str(msg.content)
                continue

            anthropic_msg: Dict[str, Any] = {"role": msg.role.value}

            # Handle content
            if isinstance(msg.content, str):
                anthropic_msg["content"] = msg.content
            else:
                # Multimodal content blocks
                anthropic_msg["content"] = msg.content

            # Handle tool results
            if msg.role == MessageRole.TOOL and msg.tool_call_id:
                anthropic_msg = {
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                    }]
                }

            converted.append(anthropic_msg)

        return system_prompt, converted

    def _prepare_tools(self, tools: Optional[List[ToolSchema]]) -> Optional[List[Dict[str, Any]]]:
        """Convert tools to Anthropic format."""
        if not tools:
            return None
        return [tool.to_anthropic_format() for tool in tools]

    def _parse_tool_calls(self, content: List[Any]) -> List[ToolCall]:
        """Extract tool calls from Anthropic response content."""
        tool_calls = []
        for block in content:
            if hasattr(block, 'type') and block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else json.loads(block.input),
                ))
        return tool_calls

    def _extract_text(self, content: List[Any]) -> str:
        """Extract text content from Anthropic response."""
        text_parts = []
        for block in content:
            if hasattr(block, 'type') and block.type == "text":
                text_parts.append(block.text)
        return "".join(text_parts)

    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSchema]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
    ) -> CompletionResponse:
        """Get a completion from Claude."""
        system_prompt, anthropic_messages = self._prepare_messages(messages)
        anthropic_tools = self._prepare_tools(tools)

        try:
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "messages": anthropic_messages,
                "max_tokens": max_tokens or self.config.max_tokens,
                "temperature": temperature if temperature is not None else self.config.temperature,
            }

            if system_prompt:
                kwargs["system"] = system_prompt

            if anthropic_tools:
                kwargs["tools"] = anthropic_tools

            if stop:
                kwargs["stop_sequences"] = stop

            response = await self._client.messages.create(**kwargs)

            # Parse response
            text_content = self._extract_text(response.content)
            tool_calls = self._parse_tool_calls(response.content)

            return CompletionResponse(
                content=text_content,
                tool_calls=tool_calls if tool_calls else None,
                usage=Usage(
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    total_tokens=response.usage.input_tokens + response.usage.output_tokens,
                ),
                finish_reason=response.stop_reason or "stop",
                model=response.model,
            )

        except anthropic.RateLimitError as e:
            raise RateLimitError(
                message=str(e),
                provider=self.name,
                retry_after=getattr(e, 'retry_after', None),
            )
        except anthropic.AuthenticationError as e:
            raise AuthenticationError(
                message=str(e),
                provider=self.name,
            )
        except anthropic.APIError as e:
            raise ProviderError(
                message=str(e),
                provider=self.name,
                status_code=getattr(e, 'status_code', None),
                retryable=getattr(e, 'status_code', 500) >= 500,
            )

    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSchema]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
    ) -> AsyncIterator[str]:
        """Stream a completion from Claude."""
        system_prompt, anthropic_messages = self._prepare_messages(messages)
        anthropic_tools = self._prepare_tools(tools)

        try:
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "messages": anthropic_messages,
                "max_tokens": max_tokens or self.config.max_tokens,
                "temperature": temperature if temperature is not None else self.config.temperature,
            }

            if system_prompt:
                kwargs["system"] = system_prompt

            if anthropic_tools:
                kwargs["tools"] = anthropic_tools

            if stop:
                kwargs["stop_sequences"] = stop

            async with self._client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text

        except anthropic.RateLimitError as e:
            raise RateLimitError(
                message=str(e),
                provider=self.name,
            )
        except anthropic.AuthenticationError as e:
            raise AuthenticationError(
                message=str(e),
                provider=self.name,
            )
        except anthropic.APIError as e:
            raise ProviderError(
                message=str(e),
                provider=self.name,
                status_code=getattr(e, 'status_code', None),
            )

    async def close(self) -> None:
        """Clean up the client."""
        if self._client:
            await self._client.close()
