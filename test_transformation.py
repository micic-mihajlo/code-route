"""Quick test for the multi-agent transformation."""

import asyncio
import os
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

    # Run async tests
    async def async_tests():
        provider = await test_provider_creation()
        await test_simple_completion(provider)
        if provider:
            await provider.close()

        # Memory tests
        await test_memory_system()
        await test_embeddings()

    asyncio.run(async_tests())

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
