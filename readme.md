# 🛤️ Code Route

> A self-improving AI assistant framework with dynamic tool creation and orchestration

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Global CLI](https://img.shields.io/badge/Global%20CLI-Ready-green.svg)](https://github.com/micic-mihajlo/code-route)

Code Route is a powerful, globally installable AI assistant that can create and execute tools dynamically, making it extensible and self-improving. Use it anywhere in your system like `gemini` or `tunacode` - but with unique capabilities for autonomous tool creation and visual enhancement.

## ✨ Features

- **🔧 Dynamic Tool Creation**: Assistant can create new tools at runtime based on your needs
- **🌐 Global CLI**: Install once, use anywhere - works in any directory
- **🎨 Beautiful Interface**: Rich terminal UI with themed colors and visual feedback
- **📱 Dual Interface**: Both CLI and web-based Streamlit interface
- **🤖 Multi-Model Support**: Switch between different AI models (OpenAI, Anthropic, etc.)
- **🔄 Self-Improving**: Tools persist and become available for future sessions
- **📊 Token Tracking**: Real-time token usage monitoring with visual progress bars
- **🛡️ Secure Execution**: Optional E2B integration for safe code execution

<div align="center">
  <img src="assets/workflow.svg" alt="Code Route Workflow" width="800"/>
</div>

## 🧩 System Architecture

Code Route is built around a modular architecture that enables its self-improving capabilities:

### Core Components

1. **Assistant Engine** (`cr.py`): The central component that:
   - Manages conversations and token usage
   - Dynamically loads and executes tools
   - Interfaces with language models via OpenRouter
   - Handles tool execution and result processing

2. **Tool System** (`tools/base.py`): The extensible foundation for all tools:
   - Defines the `BaseTool` abstract class that all tools implement
   - Provides standardized interfaces for tool execution
   - Enables dynamic discovery and loading of new tools
   - Supports tool creation during runtime

3. **System Prompts** (`prompts/system_prompts.py`): Defines the assistant's behavior:
   - Establishes identity and communication protocols
   - Provides tool usage guidelines and policies
   - Sets coding standards and security policies
   - Defines error handling and self-validation procedures

4. **Configuration** (`config.py`): Centralizes system settings:
   - Model selection and parameters
   - Token limits and conversation constraints
   - Path configurations and environment settings
   - Feature toggles and behavior controls

### Interface Options

Code Route offers two powerful interfaces to suit different workflows:

#### 💻 Command Line Interface (CLI)

```bash
uv run cr.py
```

The CLI provides a developer-focused experience with:
- Rich text formatting with syntax highlighting
- Live progress indicators for long-running operations
- Detailed token usage visualization
- Direct tool interaction with verbose output
- Lightweight resource footprint

#### 🌐 Web Interface (Streamlit)

```bash
uv run app.py
```

The web UI delivers a modern, visual experience with:
- Clean, responsive design for all devices
- Image upload and analysis capabilities
- Real-time token usage visualization
- Markdown rendering with syntax highlighting
- Tool usage indicators and execution tracking

<div align="center">
  <img src="assets/tools.svg" alt="Code Route Tool Ecosystem" width="800"/>
</div>

## 🛠️ Tool Ecosystem

Code Route's power comes from its extensive and expandable tool ecosystem:

### Core Tools
- **Tool Creator** (`toolcreator.py`): The meta-tool that enables self-improvement by generating new tools based on natural language descriptions.

### Development Tools
- **UV Package Manager** (`uvpackagemanager.py`): Manages Python dependencies with the ultra-fast UV package manager.
- **E2B Code Executor** (`e2bcodetool.py`): Runs Python code securely in an isolated sandbox environment.
- **Linting Tool** (`lintingtool.py`): Analyzes and fixes code style issues using Ruff.

### File System Tools
- **Create Folders Tool** (`createfolderstool.py`): Creates directory structures with proper permissions.
- **File Creator** (`filecreatortool.py`): Generates new files with specified content.
- **File Content Reader** (`filecontentreadertool.py`): Reads and processes file contents.
- **File Edit** (`fileedittool.py`): Modifies existing files while preserving encoding.
- **Diff Editor** (`diffeditortool.py`): Makes precise text replacements in files.

### Web Tools
- **DuckDuckGo** (`duckduckgotool.py`): Performs privacy-focused web searches.
- **Web Scraper** (`webscrapertool.py`): Extracts content from websites.
- **Browser** (`browsertool.py`): Opens URLs in the system browser.

### Utility Tools
- **Screenshot Tool** (`screenshottool.py`): Captures screen content for analysis.
- **Weather Tool** (`weathertool.py`): Retrieves weather information for locations.

## 🔄 Self-Improvement Workflow

Code Route's unique self-improvement cycle works as follows:

1. **Need Identification**: During a conversation, the assistant identifies a capability gap
2. **Tool Specification**: The assistant designs a new tool to fill this gap
3. **Code Generation**: Using the Tool Creator, it generates the Python code for the new tool
4. **Validation & Testing**: The code is validated and tested for functionality
5. **Dynamic Loading**: The new tool is automatically loaded into the running system
6. **Immediate Usage**: The assistant can immediately use the new tool in the conversation
7. **Persistent Availability**: The tool remains available for future conversations

This cycle allows Code Route to continuously evolve its capabilities based on user interactions, becoming more powerful and tailored to specific needs over time.

## 🚀 Quick Start

### One-Line Installation

```bash
curl -fsSL https://raw.githubusercontent.com/micic-mihajlo/code-route/main/install.sh | bash
```

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/micic-mihajlo/code-route.git
cd code-route

# Install with uv (recommended)
uv install
uv pip install -e .

# Or install with pip
pip install -e .
```

### Setup

1. **Initialize in any project:**
   ```bash
   code-route --init
   ```

2. **Add your API key to `.env`:**
   ```bash
   OPENROUTER_API_KEY=your_api_key_here
   ```

3. **Start the assistant:**
   ```bash
   code-route
   # or use the short alias
   cr
   ```

## 📋 Usage

### Global Commands

| Command | Description |
|---------|-------------|
| `code-route` | Start interactive assistant |
| `code-route --web` | Launch web interface |
| `code-route --init` | Initialize in current directory |
| `code-route --tools` | Show available tools |
| `code-route --status` | Show system status |
| `code-route --version` | Show version |
| `cr` | Short alias for `code-route` |

### Interactive Commands

| Command | Description |
|---------|-------------|
| `refresh` | Reload available tools |
| `reset` | Clear conversation history |
| `models` | List available models |
| `model <name>` | Switch AI model |
| `export <file>` | Export conversation |
| `quit` | Exit application |

### Example Workflow

```bash
# Initialize a new project
mkdir my-project && cd my-project
code-route --init

# Check system status
code-route --status

# Start the assistant
code-route

# In the assistant:
You: Create a tool that can analyze Python code complexity
Code Route: I'll create a code complexity analyzer tool for you...

# The tool is now available for future use!
You: refresh
Code Route: ✨ Tool list refreshed! Found new tool: PythonComplexityAnalyzer
```

## 💡 Usage Examples

### Creating a New Tool

```
User: I need a tool that can convert CSV files to JSON format.

Code Route: I can create that for you. Let me design a CSV to JSON conversion tool...
[Tool creation process happens]
✅ Created new tool: CSVToJSONTool

Now I can convert CSV files to JSON. Let me know which file you'd like to convert.
```

### Chaining Multiple Tools

```
User: Find information about climate change, summarize it, and save it to a file.

Code Route: I'll handle that with multiple tools:
1. Using DuckDuckGo to search for climate change information...
2. Analyzing and summarizing the search results...
3. Creating a file with the summary...
✅ File created: climate_change_summary.md
```

### Code Analysis and Execution

```
User: Can you analyze this Python function and optimize it?
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

Code Route: This recursive Fibonacci implementation has exponential time complexity.
Let me optimize it using dynamic programming:

```python
def fibonacci(n):
    if n <= 1:
        return n
    fib = [0, 1]
    for i in range(2, n+1):
        fib.append(fib[i-1] + fib[i-2])
    return fib[n]
```

Would you like me to test the performance difference?
```

## 🔍 Advanced Features

### Token Management

Code Route implements sophisticated token tracking to maximize the utility of context windows:

- **Real-time monitoring**: Visualizes token usage during conversations
- **Adaptive responses**: Adjusts verbosity based on available context space
- **Efficient history management**: Optimizes conversation history retention
- **Context prioritization**: Ensures critical information remains in context

### Tool Chaining

The system can automatically chain multiple tools together to solve complex problems:

- **Sequential execution**: Passes outputs from one tool as inputs to another
- **Parallel processing**: Runs independent tools simultaneously when possible
- **Error handling**: Gracefully manages failures in tool chains
- **Progress tracking**: Provides visibility into multi-step operations

### Security Features

Code Route implements robust security measures:

- **Sandboxed execution**: Runs code in isolated environments
- **Input validation**: Sanitizes all inputs to prevent injection attacks
- **Credential protection**: Securely handles API keys and sensitive data
- **Permission boundaries**: Restricts tool access to appropriate resources

## 📚 Contributing

Contributions to Code Route are welcome! Here's how you can help:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

For major changes, please open an issue first to discuss what you would like to change.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

