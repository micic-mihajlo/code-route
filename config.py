from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    # MODEL = "deepseek/deepseek-chat-v3-0324"
    #MODEL = "openai/gpt-4.1-mini"
    MODEL = "openai/o4-mini"
    # MODEL = "google/gemini-2.5-pro-preview-03-25"
    MAX_TOKENS = 8000
    MAX_CONVERSATION_TOKENS = 200000  # max tokens per convo

    # paths
    BASE_DIR = Path(__file__).parent
    TOOLS_DIR = BASE_DIR / "tools"
    PROMPTS_DIR = BASE_DIR / "prompts"

    # assistant config
    ENABLE_THINKING = True
    SHOW_TOOL_USAGE = True
    DEFAULT_TEMPERATURE = 0.45
