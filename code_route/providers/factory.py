"""Provider factory with auto-detection and configuration."""

import os
from typing import Dict, Optional, Type

from ..core.exceptions import ConfigError
from .base import BaseProvider, ProviderConfig
from .anthropic import AnthropicProvider
from .openai import OpenAIProvider
from .openrouter import OpenRouterProvider
from .local import LocalProvider


# Provider registry
PROVIDERS: Dict[str, Type[BaseProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "openrouter": OpenRouterProvider,
    "local": LocalProvider,
}

# Model prefix to provider mapping
MODEL_PREFIXES: Dict[str, str] = {
    "claude": "anthropic",
    "gpt": "openai",
    "o1": "openai",
    "anthropic/": "openrouter",
    "openai/": "openrouter",
    "google/": "openrouter",
    "meta/": "openrouter",
    "mistral/": "openrouter",
}

# Environment variable mapping
ENV_KEYS: Dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "local": "LOCAL_API_KEY",  # Usually not needed
}


class ProviderFactory:
    """
    Factory for creating LLM providers with auto-detection.

    Usage:
        # Auto-detect from environment
        provider = ProviderFactory.create()

        # Specify provider and model
        provider = ProviderFactory.create(
            provider_name="anthropic",
            model="claude-sonnet-4-20250514"
        )

        # With custom config
        provider = ProviderFactory.create(
            provider_name="openrouter",
            config=ProviderConfig(
                api_key="sk-...",
                model="anthropic/claude-sonnet-4",
                temperature=0.5,
            )
        )
    """

    @classmethod
    def create(
        cls,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        config: Optional[ProviderConfig] = None,
    ) -> BaseProvider:
        """
        Create a provider instance.

        Args:
            provider_name: Provider to use (anthropic, openai, openrouter, local).
                          If not specified, auto-detects based on available API keys.
            model: Model to use. If not specified, uses provider default.
            config: Full configuration. If not specified, builds from environment.

        Returns:
            Configured provider instance.

        Raises:
            ConfigError: If no provider can be configured.
        """
        # Determine provider
        if provider_name is None:
            if model:
                provider_name = cls._infer_provider_from_model(model)
            else:
                provider_name = cls._detect_available_provider()

        if provider_name not in PROVIDERS:
            raise ConfigError(
                f"Unknown provider: {provider_name}",
                config_key="provider",
                details={"available": list(PROVIDERS.keys())}
            )

        # Build config if not provided
        if config is None:
            config = cls._build_config(provider_name, model)

        # Create provider
        provider_class = PROVIDERS[provider_name]
        return provider_class(config)

    @classmethod
    def _infer_provider_from_model(cls, model: str) -> str:
        """Infer provider from model name."""
        model_lower = model.lower()

        # Check prefixes
        for prefix, provider in MODEL_PREFIXES.items():
            if model_lower.startswith(prefix):
                return provider

        # Default to openrouter for unknown models (it supports many)
        return "openrouter"

    @classmethod
    def _detect_available_provider(cls) -> str:
        """Detect which provider is available based on environment."""
        # Priority order: Anthropic > OpenAI > OpenRouter > Local
        priority = ["anthropic", "openai", "openrouter", "local"]

        for provider in priority:
            env_key = ENV_KEYS.get(provider)
            if env_key and os.environ.get(env_key):
                return provider

        # Check for local server
        if cls._check_local_server():
            return "local"

        raise ConfigError(
            "No LLM provider configured. Set one of: "
            "ANTHROPIC_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY",
            config_key="api_key",
        )

    @classmethod
    def _check_local_server(cls) -> bool:
        """Check if a local LLM server is running."""
        import socket

        # Check common local ports
        ports = [1234, 11434, 8080]  # LM Studio, Ollama, vLLM
        for port in ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex(('localhost', port))
                sock.close()
                if result == 0:
                    return True
            except Exception:
                pass
        return False

    @classmethod
    def _build_config(cls, provider_name: str, model: Optional[str] = None) -> ProviderConfig:
        """Build provider config from environment."""
        env_key = ENV_KEYS.get(provider_name)
        api_key = os.environ.get(env_key) if env_key else None

        # Provider-specific base URLs
        base_url = None
        if provider_name == "local":
            base_url = os.environ.get("LOCAL_API_BASE", "http://localhost:1234/v1")
        elif provider_name == "openrouter":
            base_url = "https://openrouter.ai/api/v1"

        # Model defaults
        if model is None:
            defaults = {
                "anthropic": "claude-sonnet-4-20250514",
                "openai": "gpt-4o",
                "openrouter": "anthropic/claude-sonnet-4",
                "local": "local-model",
            }
            model = defaults.get(provider_name, "")

        return ProviderConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=float(os.environ.get("LLM_TEMPERATURE", "0.7")),
            max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "8192")),
            timeout=float(os.environ.get("LLM_TIMEOUT", "120.0")),
        )

    @classmethod
    def list_available(cls) -> Dict[str, bool]:
        """List available providers and their status."""
        available = {}
        for provider in PROVIDERS:
            env_key = ENV_KEYS.get(provider)
            if provider == "local":
                available[provider] = cls._check_local_server()
            elif env_key:
                available[provider] = bool(os.environ.get(env_key))
            else:
                available[provider] = False
        return available


def get_provider(
    provider_name: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> BaseProvider:
    """
    Convenience function to get a provider.

    Args:
        provider_name: Provider to use
        model: Model to use
        **kwargs: Additional config options (api_key, temperature, etc.)

    Returns:
        Configured provider instance.
    """
    config = None
    if kwargs:
        config = ProviderConfig(
            model=model or "",
            **kwargs
        )
    return ProviderFactory.create(provider_name, model, config)
