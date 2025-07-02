# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
- **CLI Interface**: `uv run cr.py` - Interactive command-line interface with rich text formatting
- **Web Interface**: `uv run app.py` - Streamlit-based web UI with image upload capabilities

### Package Management
- **Install dependencies**: `uv install` or `uv sync`
- **Add new dependency**: `uv add <package_name>`
- **Remove dependency**: `uv remove <package_name>`

### Code Quality
- **Linting**: Use the built-in `LintingTool` or `ruff check .`
- **Formatting**: `ruff format .` (configured in pyproject.toml)
- **Type checking**: `mypy .` (optional-dependencies in pyproject.toml)

### Testing
- **Run tests**: `pytest` (configured in pyproject.toml with coverage)
- **Test specific file**: `pytest tests/test_filename.py`

## High-Level Architecture

### Core System Structure

**Code Route** is a self-improving AI assistant framework built around dynamic tool creation and orchestration. The system follows a modular architecture where tools can be created at runtime based on user needs.

**Central Components:**

1. **Assistant Engine (`cr.py`)**: The main orchestrator that:
   - Manages conversations and token usage tracking
   - Interfaces with OpenRouter API for multi-model support
   - Dynamically loads and executes tools from the tools directory
   - Handles tool chaining and result processing
   - Implements conversation history management with multimodal support

2. **Tool System (`tools/base.py` + `tools/*.py`)**: Extensible tool architecture:
   - `BaseTool` abstract class defines standardized interface for all tools
   - Tools auto-discovered and loaded from `tools/` directory
   - Runtime tool creation via `ToolCreatorTool` enables self-improvement
   - Each tool implements: `name`, `description`, `input_schema`, and `execute()`

3. **Configuration (`config.py`)**: Centralized settings management:
   - Model selection (currently supports OpenRouter models)
   - Token limits and conversation constraints
   - Feature toggles (thinking mode, tool usage display)
   - Path configurations for tools and prompts

4. **System Prompts (`prompts/system_prompts.py`)**: Comprehensive behavior definition:
   - Detailed tool usage policies and guidelines
   - Error handling and resolution procedures
   - Security and coding standards
   - Self-validation checklists

### Tool Ecosystem

The framework includes two categories of tools:

**Development Tools**: File operations, code execution, package management, linting
**Utility Tools**: Web scraping, search, weather, screenshots, browser automation

**Key Tool**: `ToolCreatorTool` enables the system to generate new tools dynamically by writing Python code that follows the `BaseTool` interface.

### Self-Improvement Workflow

1. **Need Detection**: Assistant identifies missing capability during conversation
2. **Tool Design**: Specifies requirements for new tool functionality  
3. **Code Generation**: `ToolCreatorTool` creates Python implementation
4. **Dynamic Loading**: New tool automatically becomes available
5. **Immediate Usage**: Can be used in the same conversation
6. **Persistence**: Tool remains available for future sessions

### Interface Design

**CLI Mode (`cr.py`)**: Terminal-based interface using `rich` for formatting, `prompt-toolkit` for input handling. Features token usage visualization and detailed tool execution display.

**Web Mode (`app.py`)**: Streamlit interface supporting image uploads, markdown rendering, and visual token tracking. Handles multimodal conversations with base64 image encoding.

## Important Development Notes

### Environment Setup
- Uses `uv` for fast Python package management
- Requires OpenRouter API key in `.env` file
- Optional E2B API key for secure code execution
- Python 3.9+ required

### Token Management
- Conversation token limits enforced via `Config.MAX_CONVERSATION_TOKENS`
- Real-time token tracking with progress visualization
- Automatic conversation reset when limits approached

### Tool Development
- New tools must inherit from `BaseTool` and implement all abstract methods
- Tools auto-discovered via `pkgutil.iter_modules()` in the tools directory
- Missing dependencies trigger optional installation prompts
- Tool execution results formatted as JSON when possible

### Security Considerations
- All sensitive data (API keys, tokens) handled via environment variables
- Tool execution includes error handling and input validation
- No secrets committed to repository or exposed in logs
- Sandboxed execution environments for code tools

### Configuration Management
- Model selection via `Config.MODEL` (supports various OpenRouter models)
- Temperature and token limits configurable per conversation
- Tool behavior controlled via feature flags
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