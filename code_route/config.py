import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

class Config:
    VERSION = "0.1.0"
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    
    # Available models
    AVAILABLE_MODELS = {
        "openai/gpt-4.1": "OpenAI GPT-4.1",
        "openai/gpt-4.1-mini": "OpenAI GPT-4.1 Mini", 
        "anthropic/claude-sonnet-4": "Anthropic Claude Sonnet 4",
        "x-ai/grok-3-mini-beta": "xAI Grok 3 Mini Beta",
        "anthropic/claude-3-5-haiku": "Anthropic Claude 3.5 Haiku",
        "google/gemini-2.5-pro-preview-03-25": "Google Gemini 2.5 Pro"
    }
    
    # Default model
    MODEL = os.getenv('MODEL', "openai/gpt-4.1-mini")
    MAX_TOKENS = 8000
    MAX_CONVERSATION_TOKENS = 200000  # max tokens per convo

    # paths
    BASE_DIR = Path(__file__).parent
    TOOLS_DIR = BASE_DIR / "tools"
    PROMPTS_DIR = BASE_DIR / "prompts"

    # assistant config
    ENABLE_THINKING = True
    SHOW_TOOL_USAGE = True
    DEFAULT_TEMPERATURE = 0.3
