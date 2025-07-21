# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the Code Route project.

## Development Commands

### Running the Application
- **CLI Interface**: `code-route` or `cr` - Global CLI command for interactive assistant
- **Web Interface**: `code-route --web` - Launch Streamlit-based web UI with image upload capabilities
- **Direct Python**: `uv run code_route/cli.py` - Run from source

### CLI Usage
- **Initialize project**: `code-route --init` - Set up .env file in current directory
- **Show tools**: `code-route --tools` - List all available tools
- **System status**: `code-route --status` - Check configuration and system health
- **Web interface**: `code-route --web` - Launch Streamlit interface
- **Version info**: `code-route --version`

### Package Management
- **Install dependencies**: `uv install` or `uv sync`
- **Add new dependency**: `uv add <package_name>`
- **Remove dependency**: `uv remove <package_name>`

### Code Quality
- **Linting**: `ruff check .` (configured in pyproject.toml)
- **Formatting**: `ruff format .` (configured in pyproject.toml)
- **Type checking**: `mypy .` (optional dev dependency)

### Testing
- **Run tests**: `pytest` (configured in pyproject.toml with coverage)
- **Test specific file**: `pytest tests/test_filename.py`

## High-Level Architecture

### Core System Structure

**Code Route** is a self-improving AI assistant framework built around dynamic tool creation and orchestration. The system follows a modular architecture where tools can be created at runtime based on user needs.

**Central Components:**

1. **Assistant Engine (`code_route/assistant.py`)**: The main orchestrator that:
   - Manages conversations and token usage tracking
   - Interfaces with OpenRouter API for multi-model support
   - Dynamically loads and executes tools from the tools directory
   - Handles tool chaining and result processing
   - Implements conversation history management with multimodal support

2. **CLI Interface (`code_route/cli.py`)**: Global command-line interface that:
   - Provides banner display and system status checking
   - Handles configuration validation and setup
   - Launches web interface and shows available tools
   - Manages project initialization with .env files

3. **Tool System (`code_route/tools/base.py` + `code_route/tools/*.py`)**: Extensible tool architecture:
   - `BaseTool` abstract class defines standardized interface for all tools
   - Tools auto-discovered and loaded from `code_route/tools/` directory
   - Runtime tool creation via `ToolCreatorTool` enables self-improvement
   - Each tool implements: `name`, `description`, `input_schema`, and `execute()`

4. **Configuration (`code_route/config.py`)**: Centralized settings management:
   - Model selection via OpenRouter (supports multiple providers)
   - Token limits and conversation constraints
   - Feature toggles (thinking mode, tool usage display)
   - Path configurations for tools and prompts

5. **System Prompts (`code_route/prompts/system_prompts.py`)**: Comprehensive behavior definition:
   - Detailed tool usage policies and guidelines
   - Error handling and resolution procedures
   - Security and coding standards
   - Self-validation checklists

### Tool Ecosystem

The framework includes comprehensive tools for development and productivity:

**File Operations**: `FileCreatorTool`, `FileEditTool`, `MultiEditTool`, `FileContentReaderTool`, `LSTool`, `GlobTool`, `GrepTool`
**Development Tools**: `BashTool`, `E2BCodeTool`, `LintingTool`, `UVPackageManager`, `CreateFoldersTool`, `DiffEditorTool`
**Utility Tools**: `WebScraperTool`, `DuckDuckGoTool`, `WeatherTool`, `ScreenshotTool`, `BrowserTool`
**Notebook Support**: `NotebookReadTool`, `NotebookEditTool`
**Productivity**: `TodoWriteTool`, `AgentTool`

**Key Tool**: `ToolCreatorTool` enables the system to generate new tools dynamically by writing Python code that follows the `BaseTool` interface.

### Self-Improvement Workflow

1. **Need Detection**: Assistant identifies missing capability during conversation
2. **Tool Design**: Specifies requirements for new tool functionality  
3. **Code Generation**: `ToolCreatorTool` creates Python implementation
4. **Dynamic Loading**: New tool automatically becomes available
5. **Immediate Usage**: Can be used in the same conversation
6. **Persistence**: Tool remains available for future sessions

### Interface Design

**CLI Mode (`code_route/cli.py`)**: Global command-line interface with rich terminal UI using `rich` for formatting and themed display. Features banner, status checking, tool listing, and assistant launching.

**Assistant Mode (`code_route/assistant.py`)**: Terminal-based interactive assistant using `prompt-toolkit` for input handling and `rich` for output formatting. Features token usage visualization and detailed tool execution display.

**Web Mode (`code_route/app.py`)**: Streamlit interface supporting image uploads, markdown rendering, and visual token tracking. Handles multimodal conversations with base64 image encoding and model switching.

## Important Development Notes

### Environment Setup
- Uses `uv` for fast Python package management
- Requires OpenRouter API key in `.env` file or environment variable
- Optional E2B API key for secure code execution
- Python 3.9+ required
- Global installation via `pip install -e .` or `uv sync`

### API Keys Configuration
- **Required**: `OPENROUTER_API_KEY` - Get from https://openrouter.ai/
- **Optional**: `E2B_API_KEY` - For secure code execution sandbox
- **Optional**: `MODEL` - Override default model selection
- Place in `.env` file in any project directory or set as environment variables

### Token Management
- Conversation token limits enforced via `Config.MAX_CONVERSATION_TOKENS` (200M tokens)
- Real-time token tracking with progress visualization
- Model-specific token limits via `Config.MAX_TOKENS` (8000)
- Automatic conversation management when limits approached

### Tool Development
- New tools must inherit from `BaseTool` and implement all abstract methods
- Tools auto-discovered via `pkgutil.iter_modules()` in the `code_route/tools` directory
- Missing dependencies trigger optional installation prompts
- Tool execution results formatted as JSON when possible
- Use `ToolCreatorTool` for runtime tool generation

### Security Considerations
- All sensitive data (API keys, tokens) handled via environment variables
- Tool execution includes error handling and input validation
- No secrets committed to repository or exposed in logs
- Optional E2B integration for sandboxed code execution

### Configuration Management
- Model selection via `Config.AVAILABLE_MODELS` (supports multiple OpenRouter providers)
- Default model: `moonshotai/kimi-k2` (configurable via `MODEL` env var)
- Temperature and token limits configurable per conversation
- Tool behavior controlled via feature flags (`ENABLE_THINKING`, `SHOW_TOOL_USAGE`)
- Directory paths configured for cross-platform compatibility

## Detailed Development Policies

### Git Workflow Guidelines
- **Branch naming**: Use descriptive names like `feature/tool-optimization` or `fix/token-tracking`
- **Commits**: Write atomic commits with imperative verbs ("Add tool validation", "Fix memory leak")
- **Pull requests**: Open early as drafts, address review comments promptly
- **Never force-push** without coordinating with team

### CI/CD Best Practices
- Run linters and tests locally before pushing
- If CI fails, analyze logs and fix within 3 attempts
- Don't merge until CI is fully green
- Smoke-test staging deployments before sharing

### Performance Considerations
- Avoid premature optimization but be mindful of algorithmic complexity
- Use lazy loading and caching where it materially improves response time
- Minimize memory-heavy operations unless justified
- Profile code when performance issues are suspected

### Documentation Standards
- Write docstrings for public modules, classes, and functions
- Update README when behavior changes
- Use Markdown for prose documentation with examples
- Include usage examples for new tools and features

### Error Resolution Playbook
- **Environment errors**: Report to user; avoid local fixes that mask root issues
- **Network errors**: Retry with exponential backoff; alert user if persistent
- **Dependency errors**: Pin versions explicitly; run package manager
- **Syntax/Runtime errors**: Lint and test incrementally; fix code not tests
- **Test failures**: Inspect assertions; assume code is wrong before changing tests

### Data Retention & Cleanup
- Delete temporary files, logs, and scratch data after use
- Respect user instructions on data retention windows
- Ensure local paths don't accumulate redundant artifacts
- Clean up debug outputs and development tools before commits