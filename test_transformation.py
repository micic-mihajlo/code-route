"""Quick test for the multi-agent transformation."""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def test_imports():
    """Test that all new modules import correctly."""
    print("Testing imports...")

    # Core
    from code_route.core import (
        Message, ToolCall, ToolResult, CompletionResponse,
        Event, EventType, EventBus,
        CodeRouteError, ProviderError, ToolError,
    )
    print("  [OK] core/ imports")

    # Providers
    from code_route.providers import (
        BaseProvider, ProviderCapabilities,
        AnthropicProvider, OpenAIProvider, OpenRouterProvider, LocalProvider,
        ProviderFactory, get_provider,
    )
    print("  [OK] providers/ imports OK")

    # Agents
    from code_route.agents import (
        BaseAgent, AgentRole, AgentCapabilities,
        AgentRegistry,
        OrchestratorAgent, CoderAgent, ResearcherAgent, ReviewerAgent, PlannerAgent,
    )
    print("  [OK] agents/ imports OK")

    # Tools
    from code_route.tools.base import BaseTool, ToolResult, LegacyToolWrapper, is_async_tool
    print("  [OK] tools/base.py imports OK")

    # CLI
    from code_route.cli import (
        StreamingRenderer, TokenBuffer,
        ToolPanel, AgentPanel, TokenUsagePanel, StatusBar, ConversationPanel,
        KeyBindings, InputHandler,
        CodeRouteApp,
    )
    print("  [OK] cli/ imports OK")

    # MCP
    from code_route.mcp import (
        MCPServer, create_server,
        ToolHandler, ResourceHandler,
    )
    print("  [OK] mcp/ imports OK")

    # Git
    from code_route.git import (
        GitOperations, GitStatus, GitDiff, GitCommit, GitBranch, GitError,
        GitHubOperations, PullRequest, Issue,
    )
    print("  [OK] git/ imports OK")

    # Indexer
    from code_route.indexer import (
        CodebaseIndexer, ProjectIndex, FileIndex, Symbol, SymbolKind,
        SymbolExtractor, PythonExtractor, JavaScriptExtractor, TypeScriptExtractor,
        ProjectContext, CodebaseContext,
    )
    print("  [OK] indexer/ imports OK")

    print("\nAll imports successful!")


def test_provider_factory():
    """Test provider factory and auto-detection."""
    print("\nTesting provider factory...")

    from code_route.providers import ProviderFactory

    available = ProviderFactory.list_available()
    print(f"  Available providers: {available}")

    # Check which providers have API keys
    for provider, is_available in available.items():
        status = "[OK]" if is_available else "[FAIL]"
        print(f"  {status} {provider}")


def test_event_bus():
    """Test the event bus."""
    print("\nTesting event bus...")

    from code_route.core import EventBus, Event, EventType

    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe(EventType.TOOL_COMPLETED, handler)

    async def run_test():
        await bus.publish(Event(
            type=EventType.TOOL_COMPLETED,
            data={"tool": "test", "result": "success"}
        ))
        await asyncio.sleep(0.1)  # Let handler run

    asyncio.run(run_test())

    assert len(received) == 1
    assert received[0].data["tool"] == "test"
    print("  [OK] Event bus pub/sub works")


def test_tool_result():
    """Test the new ToolResult class."""
    print("\nTesting ToolResult...")

    from code_route.tools.base import ToolResult

    # Test ok
    result = ToolResult.ok("Hello world", metadata={"lines": 1})
    assert result.success
    assert result.output == "Hello world"
    assert result.metadata["lines"] == 1
    print("  [OK] ToolResult.ok() works")

    # Test err
    result = ToolResult.err("Something went wrong")
    assert not result.success
    assert result.error == "Something went wrong"
    print("  [OK] ToolResult.err() works")

    # Test str conversion (backwards compat)
    assert str(ToolResult.ok("test")) == "test"
    assert "Error:" in str(ToolResult.err("fail"))
    print("  [OK] ToolResult str conversion works")


def test_agent_task():
    """Test agent task creation."""
    print("\nTesting AgentTask...")

    from code_route.agents.base import AgentTask, AgentRole

    task = AgentTask.create(
        "Write a hello world function",
        language="python",
        file="hello.py"
    )

    assert task.description == "Write a hello world function"
    assert task.context["language"] == "python"
    assert task.id is not None
    print(f"  [OK] AgentTask created with id: {task.id}")


async def test_provider_creation():
    """Test creating a provider (if API key available)."""
    print("\nTesting provider creation...")

    from code_route.providers import ProviderFactory

    available = ProviderFactory.list_available()

    # Try to create whichever provider is available
    for provider_name, is_available in available.items():
        if is_available:
            try:
                provider = ProviderFactory.create(provider_name=provider_name)
                print(f"  [OK] Created {provider_name} provider")
                print(f"    - Name: {provider.name}")
                print(f"    - Supports tools: {provider.capabilities.supports_tools}")
                print(f"    - Supports vision: {provider.capabilities.supports_vision}")
                return provider
            except Exception as e:
                print(f"  [FAIL] Failed to create {provider_name}: {e}")

    print("  [WARN] No provider available (set ANTHROPIC_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY)")
    return None


async def test_memory_system():
    """Test the memory and RAG system."""
    print("\nTesting memory system...")

    import tempfile
    from pathlib import Path

    # Use temp file for test DB (avoids Windows cleanup issues)
    import os
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_memory.db"

    try:
        # Test SQLite Memory
        from code_route.memory import SQLiteMemory
        from code_route.core import Message, MessageRole

        memory = SQLiteMemory(db_path=db_path)

        # Create conversation
        conv_id = await memory.create_conversation(
            project_path="/test/project",
            title="Test Conversation"
        )
        print(f"  [OK] Created conversation: {conv_id[:8]}...")

        # Save messages
        msg1 = Message(role=MessageRole.USER, content="Hello, how do I write a function?")
        msg2 = Message(role=MessageRole.ASSISTANT, content="Here's how to write a function in Python...")

        await memory.save_message(conv_id, msg1)
        await memory.save_message(conv_id, msg2)
        print("  [OK] Saved messages")

        # Retrieve messages
        messages = await memory.get_recent_messages(conv_id)
        assert len(messages) == 2
        assert messages[0].role == MessageRole.USER
        print("  [OK] Retrieved messages")

        # Test conversation listing
        convs = await memory.list_conversations(project_path="/test/project")
        assert len(convs) == 1
        assert convs[0].message_count == 2
        print("  [OK] Listed conversations")

        # Test stats
        stats = await memory.get_stats()
        assert stats["conversations"] == 1
        assert stats["messages"] == 2
        print(f"  [OK] Stats: {stats['conversations']} convs, {stats['messages']} msgs")

    finally:
        # Cleanup on Windows needs explicit handling
        try:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


async def test_embeddings():
    """Test local embeddings."""
    print("\nTesting embeddings...")

    from code_route.memory.embeddings import LocalEmbeddings, TextChunker

    # Test chunker first (no model needed)
    chunker = TextChunker(chunk_size=100, chunk_overlap=20)
    text = "This is a test. " * 20
    chunks = chunker.chunk(text)
    assert len(chunks) > 1
    print(f"  [OK] Chunker: split into {len(chunks)} chunks")

    # Test embeddings (loads model - may take a moment)
    print("  Loading embedding model (first time may download)...")
    embeddings = LocalEmbeddings()

    vec = embeddings.embed("Hello world")
    assert vec.shape[0] == embeddings.dimension
    print(f"  [OK] Embedding dimension: {embeddings.dimension}")

    # Test similarity
    vec1 = embeddings.embed("Hello world")
    vec2 = embeddings.embed("Hi there")
    vec3 = embeddings.embed("The weather is nice")

    sim_related = embeddings.similarity(vec1, vec2)
    sim_unrelated = embeddings.similarity(vec1, vec3)

    assert sim_related > sim_unrelated
    print(f"  [OK] Similarity: related={sim_related:.3f}, unrelated={sim_unrelated:.3f}")


async def test_simple_completion(provider):
    """Test a simple completion with the provider."""
    if not provider:
        print("\nSkipping completion test (no provider)")
        return

    print("\nTesting simple completion...")

    from code_route.core import Message, MessageRole

    messages = [
        Message(role=MessageRole.USER, content="Say 'Hello from Code Route!' and nothing else.")
    ]

    try:
        response = await provider.complete(messages, max_tokens=50)
        print(f"  [OK] Got response: {response.content[:100]}")
        print(f"    - Tokens used: {response.usage.total_tokens}")
    except Exception as e:
        print(f"  [FAIL] Completion failed: {e}")


def test_cli_components():
    """Test the CLI components."""
    print("\nTesting CLI components...")

    # Test TokenBuffer
    from code_route.cli.streaming import TokenBuffer, StreamState

    buffer = TokenBuffer()
    buffer.append("Hello ")
    buffer.append("world!")
    assert buffer.content == "Hello world!"
    print("  [OK] TokenBuffer append works")

    # Test code block detection
    buffer.clear()
    buffer.append("Here's code:\n```python\nprint('hi')\n```")
    assert not buffer.is_in_code_block  # Block is closed
    print("  [OK] TokenBuffer code block detection works")

    buffer.clear()
    buffer.append("```python\nprint('hi')")
    assert buffer.is_in_code_block  # Block is open
    print("  [OK] TokenBuffer detects open code blocks")

    # Test panels
    from code_route.cli.panels import (
        ToolPanel, ToolExecution, ToolStatus,
        AgentPanel, AgentNode,
        TokenUsagePanel,
        StatusBar,
        ConversationPanel,
    )

    # Tool panel
    execution = ToolExecution(
        name="test_tool",
        status=ToolStatus.SUCCESS,
        input_summary="test input",
        output_summary="test output",
        duration_ms=42,
    )
    panel = ToolPanel(execution)
    rendered = panel.render()
    assert rendered is not None
    print("  [OK] ToolPanel renders")

    # Agent panel
    root = AgentNode(
        name="Orchestrator",
        role="orchestrator",
        status="working",
        children=[
            AgentNode(name="Coder", role="coder", status="idle"),
            AgentNode(name="Researcher", role="researcher", status="idle"),
        ]
    )
    agent_panel = AgentPanel(root)
    rendered = agent_panel.render()
    assert rendered is not None
    print("  [OK] AgentPanel renders")

    # Token usage
    token_panel = TokenUsagePanel(
        input_tokens=1000,
        output_tokens=500,
        max_tokens=10000,
    )
    assert token_panel.total_tokens == 1500
    rendered = token_panel.render()
    assert rendered is not None
    print("  [OK] TokenUsagePanel renders")

    # Status bar
    status = StatusBar(model="claude-3-opus", provider="anthropic")
    status.set_status("Processing")
    rendered = status.render()
    assert rendered is not None
    print("  [OK] StatusBar renders")

    # Conversation panel
    conv = ConversationPanel()
    conv.add("user", "Hello!")
    conv.add("assistant", "Hi there!")
    assert len(conv.messages) == 2
    rendered = conv.render()
    assert rendered is not None
    print("  [OK] ConversationPanel renders")

    # Test keybindings
    from code_route.cli.keybindings import KeyBindings, KeyEvent, KeyCode, LineEditor

    bindings = KeyBindings()
    called = []

    @bindings.add("j", description="Scroll down")
    def scroll_down():
        called.append("down")

    @bindings.add("k", description="Scroll up")
    def scroll_up():
        called.append("up")

    # Test matching
    handler = bindings.get_handler(KeyEvent(char="j"))
    assert handler is not None
    handler()
    assert "down" in called
    print("  [OK] KeyBindings dispatch works")

    # Test help generation
    help_dict = bindings.get_help()
    assert "j" in help_dict
    assert "k" in help_dict
    print("  [OK] KeyBindings help generation works")

    # Test line editor
    editor = LineEditor()
    editor.insert("hello")
    assert editor.line == "hello"
    editor.move_left()
    editor.insert("X")
    assert editor.line == "hellXo"
    editor.delete_back()
    assert editor.line == "hello"
    print("  [OK] LineEditor works")

    # Test history
    editor.submit()
    editor.insert("world")
    editor.submit()
    assert len(editor.history) == 2
    editor.history_up()
    assert editor.line == "world"
    editor.history_up()
    assert editor.line == "hello"
    print("  [OK] LineEditor history works")

    print("  [OK] All CLI components work!")


def test_mcp_components():
    """Test the MCP server components."""
    print("\nTesting MCP components...")

    from code_route.mcp.handlers import ToolHandler, ResourceHandler, PromptHandler
    from pathlib import Path

    # Test ToolHandler
    tool_handler = ToolHandler()

    # Create a simple mock tool
    class MockTool:
        name = "mock_tool"
        description = "A mock tool for testing"
        input_schema = {
            "type": "object",
            "properties": {
                "input": {"type": "string"}
            }
        }

        async def execute_async(self, **kwargs):
            from code_route.tools.base import ToolResult
            return ToolResult.ok(f"Received: {kwargs.get('input', 'nothing')}")

    tool_handler.register_tool(MockTool())
    tools = tool_handler.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "mock_tool"
    print("  [OK] ToolHandler registration works")

    # Test tool retrieval
    tool = tool_handler.get_tool("mock_tool")
    assert tool is not None
    assert tool.name == "mock_tool"
    print("  [OK] ToolHandler get_tool works")

    # Test ResourceHandler
    resource_handler = ResourceHandler(base_path=Path("."))
    resources = resource_handler.list_resources()
    # Should find at least some files in current dir
    assert isinstance(resources, list)
    print(f"  [OK] ResourceHandler found {len(resources)} resources")

    # Test PromptHandler
    prompt_handler = PromptHandler()

    def test_prompt_generator(topic: str = "default"):
        return [
            {"role": "user", "content": {"type": "text", "text": f"Tell me about {topic}"}}
        ]

    prompt_handler.register_prompt(
        name="explain",
        description="Explain a topic",
        generator=test_prompt_generator,
        arguments=[{"name": "topic", "description": "Topic to explain", "required": True}],
    )

    prompts = prompt_handler.list_prompts()
    assert len(prompts) == 1
    assert prompts[0]["name"] == "explain"
    print("  [OK] PromptHandler registration works")

    # Test MCP Server creation
    from code_route.mcp import MCPServer, create_server

    server = create_server(name="test-server", version="0.0.1")
    assert server.info.name == "test-server"
    assert server.capabilities.tools == True
    print("  [OK] MCPServer creation works")

    print("  [OK] All MCP components work!")


async def test_git_operations():
    """Test Git operations."""
    print("\nTesting Git operations...")

    from code_route.git import GitOperations, GitStatus, GitDiff

    # Use the code-route repo itself for testing
    git = GitOperations(repo_path=Path("."))

    # Test is_repo
    is_repo = await git.is_repo()
    assert is_repo == True
    print("  [OK] is_repo() works")

    # Test status
    status = await git.status()
    assert isinstance(status, GitStatus)
    assert status.branch != ""
    print(f"  [OK] status() works - branch: {status.branch}")

    # Test current_branch
    branch = await git.current_branch()
    assert branch == status.branch
    print(f"  [OK] current_branch() works")

    # Test diff
    diff = await git.diff()
    assert isinstance(diff, GitDiff)
    print(f"  [OK] diff() works - {diff.file_count} changed files")

    # Test log
    commits = await git.log(count=3)
    assert len(commits) <= 3
    if commits:
        assert commits[0].hash != ""
        assert commits[0].subject != ""
    print(f"  [OK] log() works - got {len(commits)} commits")

    # Test branches
    branches = await git.branches()
    assert len(branches) > 0
    current = [b for b in branches if b.is_current]
    assert len(current) == 1
    print(f"  [OK] branches() works - {len(branches)} branches")

    print("  [OK] All Git operations work!")


def test_symbol_extraction():
    """Test symbol extraction from code."""
    print("\nTesting symbol extraction...")

    from code_route.indexer.symbols import PythonExtractor, JavaScriptExtractor, TypeScriptExtractor
    from code_route.indexer.codebase import SymbolKind

    # Test Python extraction
    py_code = '''
"""Module docstring."""

CONSTANT_VALUE = 42

class MyClass:
    """A sample class."""

    def method(self, arg: str) -> int:
        """Method docstring."""
        return 0

def standalone_function(x, y):
    """A standalone function."""
    return x + y

async def async_function():
    pass
'''

    py_extractor = PythonExtractor()
    symbols = py_extractor.extract(py_code, "test.py")

    # Check class extraction
    classes = [s for s in symbols if s.kind == SymbolKind.CLASS]
    assert len(classes) == 1
    assert classes[0].name == "MyClass"
    assert "A sample class" in classes[0].docstring
    print("  [OK] Python class extraction works")

    # Check function extraction
    functions = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
    assert len(functions) >= 2
    func_names = {f.name for f in functions}
    assert "standalone_function" in func_names
    assert "async_function" in func_names
    print("  [OK] Python function extraction works")

    # Check constant extraction
    constants = [s for s in symbols if s.kind == SymbolKind.CONSTANT]
    assert len(constants) == 1
    assert constants[0].name == "CONSTANT_VALUE"
    print("  [OK] Python constant extraction works")

    # Test import extraction
    imports = py_extractor.extract_imports("from os import path\nimport json")
    assert len(imports) == 2
    print("  [OK] Python import extraction works")

    # Test TypeScript extraction
    ts_code = '''
interface User {
    name: string;
    age: number;
}

type Status = "active" | "inactive";

enum Color {
    Red,
    Green,
    Blue
}

class UserService {
    getUser(): User {
        return { name: "test", age: 0 };
    }
}

export function createUser(name: string): User {
    return { name, age: 0 };
}
'''

    ts_extractor = TypeScriptExtractor()
    ts_symbols = ts_extractor.extract(ts_code, "test.ts")

    # Check interface extraction
    interfaces = [s for s in ts_symbols if s.kind == SymbolKind.INTERFACE]
    assert len(interfaces) == 1
    assert interfaces[0].name == "User"
    print("  [OK] TypeScript interface extraction works")

    # Check type extraction
    types = [s for s in ts_symbols if s.kind == SymbolKind.TYPE]
    assert len(types) == 1
    assert types[0].name == "Status"
    print("  [OK] TypeScript type extraction works")

    # Check enum extraction
    enums = [s for s in ts_symbols if s.kind == SymbolKind.ENUM]
    assert len(enums) == 1
    assert enums[0].name == "Color"
    print("  [OK] TypeScript enum extraction works")

    print("  [OK] All symbol extraction works!")


async def test_codebase_indexer():
    """Test codebase indexer."""
    print("\nTesting codebase indexer...")

    from code_route.indexer import CodebaseIndexer, SymbolKind, ProjectContext, CodebaseContext

    # Index the code_route package itself
    indexer = CodebaseIndexer(Path("./code_route"))
    index = await indexer.index()

    assert index is not None
    assert index.file_count > 0
    print(f"  [OK] Indexed {index.file_count} files")

    # Check languages detected
    assert "python" in index.languages
    print(f"  [OK] Languages detected: {index.languages}")

    # Check symbols found
    assert index.total_symbols > 0
    print(f"  [OK] Found {index.total_symbols} symbols")

    # Test symbol search
    classes = indexer.search("*Provider*", kind=SymbolKind.CLASS)
    assert len(classes) > 0
    print(f"  [OK] Symbol search works - found {len(classes)} Provider classes")

    # Test project structure
    structure = indexer.get_structure()
    assert "files" in structure
    assert "symbols" in structure
    assert "languages" in structure
    print(f"  [OK] Project structure generation works")

    # Test context generation
    context = CodebaseContext(indexer)
    project_ctx = context.get_project_context()

    assert project_ctx.name == "code_route"
    assert project_ctx.file_count > 0
    assert len(project_ctx.languages) > 0
    print(f"  [OK] Project context: {project_ctx.name}, {project_ctx.file_count} files")

    # Test prompt generation
    prompt = context.to_prompt()
    assert "code_route" in prompt
    assert "python" in prompt.lower()
    print(f"  [OK] Context prompt generation works ({len(prompt)} chars)")

    print("  [OK] All codebase indexer tests pass!")


def main():
    print("=" * 60)
    print("Code Route Multi-Agent Transformation Test")
    print("=" * 60)

    # Run sync tests
    test_imports()
    test_provider_factory()
    test_event_bus()
    test_tool_result()
    test_agent_task()
    test_cli_components()
    test_mcp_components()
    test_symbol_extraction()

    # Run async tests
    async def async_tests():
        provider = await test_provider_creation()
        await test_simple_completion(provider)
        if provider:
            await provider.close()

        # Memory tests
        await test_memory_system()
        await test_embeddings()

        # Git tests
        await test_git_operations()

        # Indexer tests
        await test_codebase_indexer()

    asyncio.run(async_tests())

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
