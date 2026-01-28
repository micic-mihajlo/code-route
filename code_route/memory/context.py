"""Context builder for RAG-enhanced conversations."""

import json
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..core.types import Message, MessageRole
from .sqlite import SQLiteMemory
from .vector_store import VectorStore, SearchResult

if TYPE_CHECKING:
    from .embeddings import LocalEmbeddings


class ContextBuilder:
    """
    Builds optimal context for LLM calls using RAG.

    Combines:
    1. System prompt
    2. Project context (if available)
    3. Relevant past memories via vector search
    4. Recent conversation history

    Manages token budget to maximize useful context.

    Usage:
        builder = ContextBuilder(memory, vector_store)

        messages = await builder.build(
            conversation_id="abc",
            current_query="How do I fix this bug?",
            system_prompt="You are a helpful assistant.",
            max_tokens=8000,
        )
    """

    # Rough token estimates (actual varies by tokenizer)
    CHARS_PER_TOKEN = 4

    def __init__(
        self,
        memory: SQLiteMemory,
        vector_store: VectorStore,
    ):
        """
        Initialize context builder.

        Args:
            memory: SQLite memory for conversation history
            vector_store: Vector store for semantic search
        """
        self.memory = memory
        self.vector_store = vector_store

    async def build(
        self,
        conversation_id: str,
        current_query: str,
        system_prompt: str,
        max_tokens: int = 8000,
        include_rag: bool = True,
        rag_top_k: int = 5,
        rag_min_similarity: float = 0.5,
        project_context: Optional[Dict[str, Any]] = None,
    ) -> List[Message]:
        """
        Build context messages for an LLM call.

        Args:
            conversation_id: Current conversation
            current_query: User's current query
            system_prompt: Base system prompt
            max_tokens: Maximum context tokens
            include_rag: Whether to include RAG results
            rag_top_k: Number of RAG results to consider
            rag_min_similarity: Minimum similarity for RAG results
            project_context: Optional project-specific context

        Returns:
            List of Messages ready for LLM call
        """
        messages: List[Message] = []
        token_budget = max_tokens
        token_budget -= self._estimate_tokens(system_prompt)

        # 1. Build system message with optional enhancements
        system_content = system_prompt

        # Add project context if provided
        if project_context:
            project_str = self._format_project_context(project_context)
            if self._estimate_tokens(project_str) < token_budget * 0.1:
                system_content += f"\n\n## Project Context\n{project_str}"
                token_budget -= self._estimate_tokens(project_str)

        # 2. Get RAG results if enabled
        rag_context = ""
        if include_rag:
            rag_results = await self._get_rag_context(
                query=current_query,
                conversation_id=conversation_id,
                top_k=rag_top_k,
                min_similarity=rag_min_similarity,
            )
            if rag_results:
                rag_str = self._format_rag_results(rag_results)
                rag_tokens = self._estimate_tokens(rag_str)

                # Allocate up to 20% of budget for RAG
                if rag_tokens < token_budget * 0.2:
                    rag_context = rag_str
                    token_budget -= rag_tokens

        if rag_context:
            system_content += f"\n\n## Relevant Past Context\n{rag_context}"

        messages.append(Message(role=MessageRole.SYSTEM, content=system_content))

        # 3. Add conversation history (reserve tokens for current query)
        query_tokens = self._estimate_tokens(current_query) + 100  # buffer
        history_budget = token_budget - query_tokens

        history_messages = await self._get_history_messages(
            conversation_id=conversation_id,
            max_tokens=history_budget,
        )
        messages.extend(history_messages)

        # 4. Add current query
        messages.append(Message(role=MessageRole.USER, content=current_query))

        return messages

    async def _get_rag_context(
        self,
        query: str,
        conversation_id: str,
        top_k: int,
        min_similarity: float,
    ) -> List[SearchResult]:
        """Get relevant context via vector search."""
        # Search in all conversations except current one
        # to find relevant past context
        results = await self.vector_store.search(
            query=query,
            top_k=top_k * 2,  # Get more, filter later
            min_similarity=min_similarity,
        )

        # Filter out results from current conversation
        # (we'll include recent history directly)
        filtered = [
            r for r in results
            if r.conversation_id != conversation_id
        ]

        return filtered[:top_k]

    async def _get_history_messages(
        self,
        conversation_id: str,
        max_tokens: int,
    ) -> List[Message]:
        """Get recent conversation history within token budget."""
        stored_messages = await self.memory.get_messages(conversation_id)

        if not stored_messages:
            return []

        # Convert to Messages and estimate tokens
        messages: List[Message] = []
        total_tokens = 0

        # Work backwards from most recent
        for stored in reversed(stored_messages):
            msg = stored.to_message()
            content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
            msg_tokens = self._estimate_tokens(content)

            if total_tokens + msg_tokens > max_tokens:
                break

            messages.insert(0, msg)  # Insert at beginning to maintain order
            total_tokens += msg_tokens

        return messages

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate."""
        return len(text) // self.CHARS_PER_TOKEN

    def _format_project_context(self, context: Dict[str, Any]) -> str:
        """Format project context for inclusion in prompt."""
        parts = []
        for key, value in context.items():
            if isinstance(value, str):
                if len(value) > 200:
                    value = value[:200] + "..."
                parts.append(f"- **{key}**: {value}")
            elif isinstance(value, (list, dict)):
                parts.append(f"- **{key}**: {json.dumps(value, indent=2)[:200]}")
            else:
                parts.append(f"- **{key}**: {value}")
        return "\n".join(parts)

    def _format_rag_results(self, results: List[SearchResult]) -> str:
        """Format RAG results for inclusion in prompt."""
        if not results:
            return ""

        parts = []
        for i, result in enumerate(results, 1):
            text = result.text
            if len(text) > 300:
                text = text[:300] + "..."

            similarity_pct = int(result.similarity * 100)
            parts.append(f"{i}. [{similarity_pct}% relevant] {text}")

        return "\n".join(parts)


class ConversationManager:
    """
    High-level manager for conversations with memory.

    Combines SQLiteMemory, VectorStore, and ContextBuilder
    for a complete conversation management solution.

    Usage:
        manager = ConversationManager()

        # Start or continue conversation
        conv_id = await manager.get_or_create_conversation(project_path="/my/project")

        # Build context for LLM
        messages = await manager.build_context(conv_id, "How do I fix this?")

        # Save messages
        await manager.save_exchange(conv_id, user_msg, assistant_msg)
    """

    def __init__(
        self,
        memory: Optional[SQLiteMemory] = None,
        vector_store: Optional[VectorStore] = None,
    ):
        """Initialize with optional custom components."""
        self.memory = memory or SQLiteMemory()
        self.vector_store = vector_store or VectorStore()
        self.context_builder = ContextBuilder(self.memory, self.vector_store)

    async def get_or_create_conversation(
        self,
        project_path: Optional[str] = None,
        reuse_recent: bool = True,
        recent_threshold_hours: int = 24,
    ) -> str:
        """
        Get existing conversation or create new one.

        Args:
            project_path: Project to associate with
            reuse_recent: Whether to reuse recent conversations
            recent_threshold_hours: How old a conversation can be to reuse

        Returns:
            Conversation ID
        """
        if reuse_recent and project_path:
            # Look for recent conversation for this project
            conversations = await self.memory.list_conversations(
                project_path=project_path,
                limit=1,
            )

            if conversations:
                from datetime import datetime, timedelta
                recent = conversations[0]
                threshold = datetime.now() - timedelta(hours=recent_threshold_hours)

                if recent.updated_at > threshold:
                    return recent.id

        # Create new conversation
        return await self.memory.create_conversation(project_path=project_path)

    async def build_context(
        self,
        conversation_id: str,
        query: str,
        system_prompt: str = "You are a helpful coding assistant.",
        max_tokens: int = 8000,
        **kwargs,
    ) -> List[Message]:
        """Build context for an LLM call."""
        return await self.context_builder.build(
            conversation_id=conversation_id,
            current_query=query,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            **kwargs,
        )

    async def save_exchange(
        self,
        conversation_id: str,
        user_message: Message,
        assistant_message: Message,
        index_for_rag: bool = True,
    ) -> None:
        """
        Save a user-assistant exchange.

        Args:
            conversation_id: Conversation to save to
            user_message: User's message
            assistant_message: Assistant's response
            index_for_rag: Whether to index for RAG search
        """
        # Save messages
        user_id = await self.memory.save_message(conversation_id, user_message)
        assistant_id = await self.memory.save_message(conversation_id, assistant_message)

        # Index for RAG
        if index_for_rag:
            user_content = user_message.content if isinstance(user_message.content, str) else str(user_message.content)
            assistant_content = assistant_message.content if isinstance(assistant_message.content, str) else str(assistant_message.content)

            # Index substantial messages
            if len(user_content) > 50:
                await self.vector_store.add_text(
                    user_content,
                    conversation_id=conversation_id,
                    message_id=user_id,
                )

            if len(assistant_content) > 100:
                await self.vector_store.add_text(
                    assistant_content,
                    conversation_id=conversation_id,
                    message_id=assistant_id,
                )

    async def search_history(
        self,
        query: str,
        top_k: int = 10,
        project_path: Optional[str] = None,
    ) -> List[SearchResult]:
        """Search across conversation history."""
        if project_path:
            # Get conversations for this project
            conversations = await self.memory.list_conversations(project_path=project_path)
            conv_ids = [c.id for c in conversations]

            if conv_ids:
                return await self.vector_store.search_in_conversations(
                    query=query,
                    conversation_ids=conv_ids,
                    top_k=top_k,
                )

        return await self.vector_store.search(query=query, top_k=top_k)
