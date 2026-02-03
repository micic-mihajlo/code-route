"""OpenRouter provider implementation."""

import json
from typing import Any, AsyncIterator, Dict, List, Optional

from ..core.types import CompletionResponse, Message, MessageRole, ToolCall, ToolSchema, Usage
from ..core.exceptions import ProviderError, RateLimitError, AuthenticationError
from .base import BaseProvider, ProviderCapabilities, ProviderConfig

try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class OpenRouterProvider(BaseProvider):
    """
    OpenRouter provider for multi-model access.

    Provides unified access to Claude, GPT, Gemini, Llama, and many other models
    through a single API.
    """

    BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL = "anthropic/claude-sonnet-4"

    # Model capability hints
    VISION_MODELS = {
        "anthropic/claude-sonnet-4",
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "openai/gpt-4-turbo",
        "google/gemini-2.0-flash",
        "google/gemini-pro-vision",
    }

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if not HAS_OPENAI:
            raise ImportError("openai package required: pip install openai")

        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or self.BASE_URL,
            timeout=config.timeout,
            default_headers={
                "HTTP-Referer": config.extra.get("referer", "https://github.com/code-route"),
                "X-Title": config.extra.get("title", "Code Route"),
            }
        )
        self._model = config.model or self.DEFAULT_MODEL

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def capabilities(self) -> ProviderCapabilities:
        # Capabilities depend on the model
        supports_vision = self._model in self.VISION_MODELS or any(
            vm in self._model for vm in ["claude", "gpt-4", "gemini"]
        )
        return ProviderCapabilities(
            supports_tools=True,
            supports_vision=supports_vision,
            supports_streaming=True,
            supports_system_messages=True,
            max_tokens=8192,
            context_window=128000,
        )

    def _prepare_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert messages to OpenRouter format (OpenAI-compatible)."""
        converted = []

        for msg in messages:
            # OpenRouter has quirks with system messages for some models
            role = msg.role.value

            openrouter_msg: Dict[str, Any] = {
                "role": role,
                "content": msg.content,
            }

            # Handle tool results
            if msg.role == MessageRole.TOOL:
                openrouter_msg["tool_call_id"] = msg.tool_call_id
                if msg.name:
                    openrouter_msg["name"] = msg.name

            # Handle assistant messages with tool calls
            if msg.tool_calls:
                openrouter_msg["tool_calls"] = [
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

            converted.append(openrouter_msg)

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
        """Get a completion from OpenRouter."""
        openrouter_messages = self._prepare_messages(messages)
        openrouter_tools = self._prepare_tools(tools)

        try:
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "messages": openrouter_messages,
                "max_tokens": max_tokens or self.config.max_tokens,
                "temperature": temperature if temperature is not None else self.config.temperature,
            }

            if openrouter_tools:
                kwargs["tools"] = openrouter_tools

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
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                raise RateLimitError(message=str(e), provider=self.name)
            elif "unauthorized" in error_str or "401" in error_str or "invalid api key" in error_str:
                raise AuthenticationError(message=str(e), provider=self.name)
            else:
                raise ProviderError(
                    message=str(e),
                    provider=self.name,
                    retryable="500" in error_str or "502" in error_str or "503" in error_str,
                )

    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSchema]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
    ) -> AsyncIterator[str]:
        """Stream a completion from OpenRouter."""
        openrouter_messages = self._prepare_messages(messages)
        openrouter_tools = self._prepare_tools(tools)

        try:
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "messages": openrouter_messages,
                "max_tokens": max_tokens or self.config.max_tokens,
                "temperature": temperature if temperature is not None else self.config.temperature,
                "stream": True,
            }

            if openrouter_tools:
                kwargs["tools"] = openrouter_tools

            if stop:
                kwargs["stop"] = stop

            stream = await self._client.chat.completions.create(**kwargs)

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            error_str = str(e).lower()
            if "rate limit" in error_str:
                raise RateLimitError(message=str(e), provider=self.name)
            elif "unauthorized" in error_str or "invalid api key" in error_str:
                raise AuthenticationError(message=str(e), provider=self.name)
            else:
                raise ProviderError(message=str(e), provider=self.name)

    async def close(self) -> None:
        """Clean up the client."""
        if self._client:
            await self._client.close()
