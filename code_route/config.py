import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# minimal comment

class Config:
    VERSION = "0.1.0"
    DEFAULT_MODEL = "openai/gpt-5-codex"

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

    LMSTUDIO_API_BASE = os.getenv("LMSTUDIO_API_BASE", "http://localhost:1234/v1")
    LMSTUDIO_API_KEY = os.getenv("LMSTUDIO_API_KEY", "lmstudio")

    _OPENROUTER_SETTINGS = {
        "provider": "openrouter",
        "base_url": OPENROUTER_BASE_URL,
        "api_key": OPENROUTER_API_KEY,
    }

    MODEL_SETTINGS = {
        "openai/gpt-5-codex": {
            "display_name": "OpenAI GPT-5 Codex",
            **_OPENROUTER_SETTINGS,
        },
        "anthropic/claude-sonnet-4": {
            "display_name": "Anthropic Claude Sonnet 4",
            **_OPENROUTER_SETTINGS,
        },
        "x-ai/grok-3-mini-beta": {
            "display_name": "xAI Grok 3 Mini Beta",
            **_OPENROUTER_SETTINGS,
        },
        "anthropic/claude-3-5-haiku": {
            "display_name": "Anthropic Claude 3.5 Haiku",
            **_OPENROUTER_SETTINGS,
        },
        "google/gemini-2.5-pro-preview-03-25": {
            "display_name": "Google Gemini 2.5 Pro",
            **_OPENROUTER_SETTINGS,
        },
        "moonshotai/kimi-k2:free": {
            "display_name": "Moonshot AI Kimi K2 Free",
            **_OPENROUTER_SETTINGS,
        },
        "moonshotai/kimi-k2": {
            "display_name": "Moonshot AI Kimi K2",
            **_OPENROUTER_SETTINGS,
        },
        "lmstudio/local": {
            "display_name": "LM Studio Local",
            "provider": "lmstudio",
            "base_url": LMSTUDIO_API_BASE,
            "api_key": LMSTUDIO_API_KEY,
        },
    }

    AVAILABLE_MODELS = {model: settings["display_name"] for model, settings in MODEL_SETTINGS.items()}

    MODEL = os.getenv("MODEL", DEFAULT_MODEL)
    MAX_TOKENS = 20000
    MAX_CONVERSATION_TOKENS = 20000000  # max tokens per convo

    # paths
    BASE_DIR = Path(__file__).parent
    TOOLS_DIR = BASE_DIR / "tools"
    PROMPTS_DIR = BASE_DIR / "prompts"

    # assistant config
    ENABLE_THINKING = True
    SHOW_TOOL_USAGE = True
    DEFAULT_TEMPERATURE = 0.2
