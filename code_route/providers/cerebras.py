"""Cerebras provider implementation.

Cerebras Cloud offers extremely fast inference for open models.
Uses OpenAI-compatible API.
"""

from typing import Any, AsyncIterator, Dict, List, Optional

from ..core.types import CompletionResponse, Message, ToolCall, ToolSchema, Usage
from ..core.exceptions import ProviderError, RateLimitError, AuthenticationError
from .base import BaseProvider, ProviderCapabilities, ProviderConfig

try:
    import openai
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class CerebrasProvider(BaseProvider):
    """
    Cerebras Cloud provider.

    Provides extremely fast inference for open models including:
    - llama3.1-8b
    - llama3.1-70b
    - llama3.3-70b
    - llama-4-scout-17b-16e-instruct (Llama 4)

    Uses OpenAI-compatible API.
    """

    BASE_URL = "https://api.cerebras.ai/v1"
    DEFAULT_MODEL = "zai-glm-4.7"

    # Available models on Cerebras
    AVAILABLE_MODELS = [
        "zai-glm-4.7",
        "llama-3.3-70b",
        "llama3.1-8b",
        "qwen-3-32b",
        "qwen-3-235b-a22b-instruct-2507",
        "gpt-oss-120b",
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if not HAS_OPENAI:
            raise ImportError("openai package required: pip install openai")

        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or self.BASE_URL,
            timeout=config.timeout,
        )
        self._model = config.model or self.DEFAULT_MODEL

    @property
    def name(self) -> str:
        return "cerebras"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_tools=True,
            supports_vision=False,  # Cerebras doesn't support vision yet
            supports_streaming=True,
            supports_system_messages=True,
            max_tokens=8192,
            context_window=131072,  # 128K context for Llama models
        )

    def _prepare_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert messages to OpenAI format."""
        from ..core.types import MessageRole
        import json

        converted = []

        for msg in messages:
            openai_msg: Dict[str, Any] = {
                "role": msg.role.value,
                "content": msg.content,
            }

            # Handle tool results
            if msg.role == MessageRole.TOOL:
                openai_msg["tool_call_id"] = msg.tool_call_id
                if msg.name:
                    openai_msg["name"] = msg.name

            # Handle assistant messages with tool calls
            if msg.tool_calls:
                openai_msg["tool_calls"] = [
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

            converted.append(openai_msg)

        return converted

    def _parse_tool_calls(self, tool_calls: Optional[List[Any]]) -> List[ToolCall]:
        """Extract tool calls from response."""
        import json

        if not tool_calls:
            return []

        parsed = []
        for tc in tool_calls:
            try:
                arguments = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, AttributeError):
                arguments = tc.function.arguments

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
        """Get a completion from Cerebras."""
        openai_messages = self._prepare_messages(messages)
        openai_tools = self._prepare_tools(tools)

        try:
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "messages": openai_messages,
                "max_tokens": max_tokens or self.config.max_tokens,
                "temperature": temperature if temperature is not None else self.config.temperature,
            }

            if openai_tools:
                kwargs["tools"] = openai_tools

            if stop:
                kwargs["stop"] = stop

            response = await self._client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            # For reasoning models: content has the answer, reasoning has the thinking
            # Only fall back to reasoning if content is empty AND model finished (not truncated)
            content = choice.message.content
            if not content and choice.finish_reason == "stop":
                # Model finished but no content - use reasoning as fallback
                if hasattr(choice.message, 'reasoning') and choice.message.reasoning:
                    content = choice.message.reasoning

            return CompletionResponse(
                content=content or "",
                tool_calls=self._parse_tool_calls(choice.message.tool_calls) or None,
                usage=Usage(
                    prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                    completion_tokens=response.usage.completion_tokens if response.usage else 0,
                    total_tokens=response.usage.total_tokens if response.usage else 0,
                ),
                finish_reason=choice.finish_reason or "stop",
                model=response.model,
            )

        except openai.RateLimitError as e:
            raise RateLimitError(
                message=str(e),
                provider=self.name,
            )
        except openai.AuthenticationError as e:
            raise AuthenticationError(
                message=str(e),
                provider=self.name,
            )
        except openai.APIError as e:
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
        """Stream a completion from Cerebras."""
        openai_messages = self._prepare_messages(messages)
        openai_tools = self._prepare_tools(tools)

        try:
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "messages": openai_messages,
                "max_tokens": max_tokens or self.config.max_tokens,
                "temperature": temperature if temperature is not None else self.config.temperature,
                "stream": True,
            }

            if openai_tools:
                kwargs["tools"] = openai_tools

            if stop:
                kwargs["stop"] = stop

            stream = await self._client.chat.completions.create(**kwargs)

            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    # Prioritize content (the actual answer) over reasoning (thinking)
                    if delta.content:
                        yield delta.content

        except openai.RateLimitError as e:
            raise RateLimitError(
                message=str(e),
                provider=self.name,
            )
        except openai.AuthenticationError as e:
            raise AuthenticationError(
                message=str(e),
                provider=self.name,
            )
        except openai.APIError as e:
            raise ProviderError(
                message=str(e),
                provider=self.name,
                status_code=getattr(e, 'status_code', None),
            )

    async def close(self) -> None:
        """Clean up the client."""
        if self._client:
            await self._client.close()
