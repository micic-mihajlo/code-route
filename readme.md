# Code Route 🛤️

A self-improving AI assistant framework designed to create and manage AI tools dynamically during conversations. Code Route serves developers by providing a programmable AI assistant that can adapt to new tasks without requiring manual coding of new capabilities.

## Overview

Code Route is a sophisticated framework that allows AI models to expand their own capabilities through dynamic tool creation. During conversations, the AI can identify needs for new tools, design them, and implement them automatically. This self-improving architecture means the framework becomes more powerful the more you use it.

The system enables users to interact with an AI assistant through both command-line and web interfaces, allowing the assistant to leverage various tools to solve complex problems, analyze code, perform web searches, manipulate files, and even create new tools on its own.

The unique value of Code Route lies in its ability to autonomously identify the need for new capabilities and implement them as reusable tools during conversations, effectively expanding its own functionality over time. By using the OpenRouter API, the system can access various language models while maintaining a consistent interface.

## Installation

For the best possible experience, install uv:

### macOS and Linux
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
# Or using wget if curl is not available:
# wget -qO- https://astral.sh/uv/install.sh | sh

# Clone and setup
git clone https://github.com/micic-mihajlo/cr-py.git
cd cr-py
uv venv
source .venv/bin/activate

# Run web interface
uv run app.py

# Or run CLI
uv run cr.py
```

### Windows
```powershell
# Install uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Clone and setup
git clone https://github.com/micic-mihajlo/cr-py.git
cd cr-py
uv venv
.venv\Scripts\activate

# Run web interface
uv run app.py

# Or run CLI
uv run cr.py
```

## Interface Options

### 1. Web Interface 🌐
A sleek, modern web UI with features like:
- Real-time token usage visualization
- Image upload and analysis capabilities
- Markdown rendering with syntax highlighting
- Responsive design for all devices
- Tool usage indicators
- Clean, minimal interface

To run the web interface:
```bash
# Using uv (recommended)
uv run app.py

# Then open your browser to:
http://localhost:5000
```

### 2. Command Line Interface (CLI) 💻
A powerful terminal-based interface with:
- Rich text formatting
- Progress indicators
- Token usage visualization
- Direct tool interaction
- Detailed debugging output

To run the CLI:
```bash
# Using uv (recommended)
uv run cr.py
```

Choose the interface that best suits your workflow:
- Web UI: Great for visual work, image analysis, and a more modern experience
- CLI: Perfect for developers, system integration, and terminal workflows

## Self-Improvement Features
- 🧠 Autonomous tool identification and creation
- 🔄 Dynamic capability expansion during conversations
- 🎯 Smart tool dependency management
- 📈 Learning from tool usage patterns
- 🔍 Automatic identification of capability gaps
- 🛠️ Self-optimization of existing tools

## Core Features
- 🔨 Dynamic tool creation and loading
- 🔄 Hot-reload capability for new tools
- 🎨 Rich console interface with progress indicators
- 🧩 Tool abstraction framework with clean interfaces
- 📝 Automated tool code generation
- 🔌 Integration with various AI models through OpenRouter
- 💬 Persistent conversation history with token management
- 🛠️ Real-time tool usage display
- 🔄 Automatic tool chaining support
- ⚡ Dynamic module importing system
- 📊 Advanced token tracking
- 🎯 Precise context window management
- 🔍 Enhanced error handling and debugging
- 💾 Conversation state management

## Project Structure
```
cr-py/
├── app.py             # Web interface server (Streamlit)
├── cr.py              # Core assistant implementation and CLI interface
├── config.py          # Configuration settings
├── tools/             # Tool implementations
│   ├── base.py        # Base tool class
│   └── ...           # Generated and custom tools
└── prompts/           # System prompts
    └── system_prompts.py
```

## Key Components

### Assistant Class
The core Assistant class provides:
- Dynamic tool loading and management
- Real-time conversation handling with token tracking
- Automatic tool creation and validation
- Tool execution and chaining
- Rich console output with progress indicators
- Token usage optimization

### Configuration Options
The assistant supports various configuration options through the Config class:
- MODEL: AI model specification (via OpenRouter)
- MAX_TOKENS: Maximum tokens for individual responses
- MAX_CONVERSATION_TOKENS: Total token limit for conversations
- TOOLS_DIR: Directory for tool storage
- SHOW_TOOL_USAGE: Toggle tool usage display
- ENABLE_THINKING: Toggle thinking indicator
- DEFAULT_TEMPERATURE: Model temperature setting

## Built-in Tools
Code Route comes with a comprehensive set of pre-built tools:

### Core Tools
- 🛠️ **Tool Creator** (`toolcreator`): Creates new tools based on natural language descriptions, enabling the framework's self-improvement capabilities.

### Development Tools
- 📦 **UV Package Manager** (`uvpackagemanager`): Interface to the UV package manager for Python dependency management.
- 🐍 **E2B Code Executor** (`e2bcodetool`): Securely executes Python code in a sandboxed environment.
- 🔍 **Linting Tool** (`lintingtool`): Runs the Ruff linter on Python files.

### File System Tools
- 📂 **Create Folders Tool** (`createfolderstool`): Creates new directories and nested directory structures.
- 📝 **File Creator** (`filecreatortool`): Creates new files with specified content.
- 📖 **File Content Reader** (`filecontentreadertool`): Reads content from multiple files simultaneously.
- ✏️ **File Edit** (`fileedittool`): Advanced file editing with support for full content replacement and partial edits.
- 🔄 **Diff Editor** (`diffeditortool`): Performs precise text replacements in files by matching exact substrings.

### Web Tools
- 🔍 **DuckDuckGo** (`duckduckgotool`): Performs web searches using DuckDuckGo.
- 🌐 **Web Scraper** (`webscrapertool`): Intelligently extracts readable content from web pages.
- 🌍 **Browser** (`browsertool`): Opens URLs in the system's default web browser.

### Utility Tools
- 📸 **Screenshot Tool** (`screenshottool`): Captures screenshots of the entire screen or specific regions.
- 🌦️ **Weather Tool** (`weathertool`): Retrieves weather information for locations.

Each tool is designed to be:
- Self-documenting with detailed descriptions
- Error-resistant with comprehensive error handling
- Composable for complex operations
- Secure with proper input validation
- Cross-platform compatible where applicable

The tools are dynamically loaded and can be extended during runtime through the Tool Creator, allowing the assistant to continuously expand its capabilities based on user needs.

## API Keys Required
1. **OpenRouter API Key**: Required for accessing AI models through OpenRouter. Get your key at [openrouter.ai](https://openrouter.ai/)
2. **E2B API Key** (optional): Required for Python code execution capabilities. Get your key at [e2b.dev](https://e2b.dev/)

Add these to your `.env` file:

```bash
OPENROUTER_API_KEY=your_openrouter_key
E2B_API_KEY=your_e2b_key
```

## Requirements
- Python 3.8+
- OpenRouter API Key
- Required packages in `requirements.txt`
- Rich terminal support

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License
MIT

