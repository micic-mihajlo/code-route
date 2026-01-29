"""
Session management for persistent conversations.

Provides Claude Code-like session persistence:
- Conversations persist across restarts
- Automatic project-based session detection
- RAG-enhanced context from past conversations
- Session resume and history browsing
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.types import Message, MessageRole
from .sqlite import SQLiteMemory, StoredMessage, Conversation
from .vector_store import VectorStore, SearchResult
from .context import ContextBuilder, ConversationManager
from .embeddings import LocalEmbeddings

# Alias for type hints
ConversationInfo = Conversation


@dataclass
class SessionConfig:
    """Configuration for session behavior."""

    # Where to store the database
    db_path: Optional[Path] = None

    # Auto-resume recent sessions for same project
    auto_resume: bool = True
    auto_resume_hours: int = 24

    # RAG settings
    enable_rag: bool = True
    rag_top_k: int = 5
    rag_min_similarity: float = 0.4

    # Context settings
    max_context_tokens: int = 8000
    max_history_messages: int = 50

    # Project context files to look for
    project_context_files: List[str] = field(default_factory=lambda: [
        "CLAUDE.md",
        ".claude/config.md",
        "README.md",
        "CONTRIBUTING.md",
    ])

    def __post_init__(self):
        if self.db_path is None:
            # Default to user's home directory
            self.db_path = Path.home() / ".code-route" / "conversations.db"


@dataclass
class ProjectContext:
    """Context about the current project."""

    path: str
    name: str
    has_git: bool = False
    branch: Optional[str] = None
    context_file: Optional[str] = None
    context_content: Optional[str] = None

    def to_prompt(self) -> str:
        """Format as prompt text."""
        parts = [f"**Project**: {self.name}"]
        parts.append(f"**Path**: {self.path}")

        if self.has_git and self.branch:
            parts.append(f"**Git Branch**: {self.branch}")

        if self.context_content:
            # Truncate if too long
            content = self.context_content
            if len(content) > 2000:
                content = content[:2000] + "\n\n...(truncated)"
            parts.append(f"\n**Project Guidelines**:\n{content}")

        return "\n".join(parts)


class SessionManager:
    """
    Manages conversation sessions with persistence and RAG.

    Provides Claude Code-like experience:
    - Sessions persist to SQLite
    - Auto-resumes recent sessions for same project
    - RAG searches past conversations for context
    - Project-aware context building

    Usage:
        session = SessionManager()

        # Start or resume session for current directory
        await session.start(project_path="/my/project")

        # Add messages
        await session.add_user_message("How do I fix this?")
        response = await get_llm_response(session.get_context())
        await session.add_assistant_message(response)

        # Session auto-saves to SQLite
    """

    def __init__(self, config: Optional[SessionConfig] = None):
        """Initialize session manager."""
        self.config = config or SessionConfig()

        # Ensure database directory exists
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.memory = SQLiteMemory(db_path=self.config.db_path)
        self.embeddings = LocalEmbeddings() if self.config.enable_rag else None
        self.vector_store = VectorStore(
            embeddings=self.embeddings,
            db_path=self.config.db_path.parent / "vectors.db"
        ) if self.config.enable_rag else None

        self.context_builder = ContextBuilder(
            memory=self.memory,
            vector_store=self.vector_store,
        ) if self.vector_store else None

        # Current session state
        self.conversation_id: Optional[str] = None
        self.project_context: Optional[ProjectContext] = None
        self._messages_cache: List[Message] = []

    async def start(
        self,
        project_path: Optional[str] = None,
        force_new: bool = False,
    ) -> str:
        """
        Start or resume a session.

        Args:
            project_path: Project directory (defaults to cwd)
            force_new: Force new session even if recent one exists

        Returns:
            Conversation ID
        """
        project_path = project_path or os.getcwd()

        # Detect project context
        self.project_context = await self._detect_project_context(project_path)

        if not force_new and self.config.auto_resume:
            # Try to find recent session for this project
            existing = await self._find_recent_session(project_path)
            if existing:
                self.conversation_id = existing
                self._messages_cache = await self._load_messages()
                return self.conversation_id

        # Create new session
        self.conversation_id = await self.memory.create_conversation(
            project_path=project_path,
            title=f"Session in {self.project_context.name}",
        )
        self._messages_cache = []

        return self.conversation_id

    async def _find_recent_session(self, project_path: str) -> Optional[str]:
        """Find a recent session for this project."""
        conversations = await self.memory.list_conversations(
            project_path=project_path,
            limit=1,
        )

        if not conversations:
            return None

        recent = conversations[0]
        threshold = datetime.now() - timedelta(hours=self.config.auto_resume_hours)

        if recent.updated_at > threshold:
            return recent.id

        return None

    async def _detect_project_context(self, project_path: str) -> ProjectContext:
        """Detect project context from directory."""
        path = Path(project_path)

        context = ProjectContext(
            path=str(path),
            name=path.name,
        )

        # Check for git
        git_dir = path / ".git"
        if git_dir.exists():
            context.has_git = True
            try:
                import subprocess
                result = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=path,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    context.branch = result.stdout.strip()
            except Exception:
                pass

        # Look for context files
        for filename in self.config.project_context_files:
            filepath = path / filename
            if filepath.exists():
                try:
                    context.context_file = filename
                    context.context_content = filepath.read_text(
                        encoding="utf-8",
                        errors="replace"
                    )
                    break  # Use first found
                except Exception:
                    pass

        return context

    async def add_user_message(self, content: str) -> str:
        """
        Add a user message to the session.

        Args:
            content: Message content

        Returns:
            Message ID
        """
        if not self.conversation_id:
            raise RuntimeError("Session not started. Call start() first.")

        message = Message(role=MessageRole.USER, content=content)
        self._messages_cache.append(message)

        # Save to database
        message_id = await self.memory.save_message(self.conversation_id, message)

        # Index for RAG
        if self.vector_store and len(content) > 50:
            await self.vector_store.add_text(
                content,
                conversation_id=self.conversation_id,
                message_id=message_id,
            )

        return message_id

    async def add_assistant_message(self, content: str) -> str:
        """
        Add an assistant message to the session.

        Args:
            content: Message content

        Returns:
            Message ID
        """
        if not self.conversation_id:
            raise RuntimeError("Session not started. Call start() first.")

        message = Message(role=MessageRole.ASSISTANT, content=content)
        self._messages_cache.append(message)

        # Save to database
        message_id = await self.memory.save_message(self.conversation_id, message)

        # Index for RAG (index longer responses)
        if self.vector_store and len(content) > 100:
            await self.vector_store.add_text(
                content,
                conversation_id=self.conversation_id,
                message_id=message_id,
            )

        return message_id

    async def add_tool_result(self, tool_name: str, result: str) -> str:
        """Add a tool execution result."""
        if not self.conversation_id:
            raise RuntimeError("Session not started. Call start() first.")

        # Store as a tool message
        message = Message(
            role=MessageRole.USER,  # Tool results go as user context
            content=f"[Tool: {tool_name}]\n{result}",
        )

        return await self.memory.save_message(self.conversation_id, message)

    async def build_context(
        self,
        current_query: str,
        system_prompt: str,
        max_tokens: Optional[int] = None,
    ) -> List[Message]:
        """
        Build context for an LLM call with RAG.

        Args:
            current_query: Current user query
            system_prompt: Base system prompt
            max_tokens: Max context tokens

        Returns:
            List of messages for LLM
        """
        max_tokens = max_tokens or self.config.max_context_tokens

        if self.context_builder:
            # Use full RAG-enhanced context building
            project_dict = None
            if self.project_context:
                project_dict = {
                    "name": self.project_context.name,
                    "path": self.project_context.path,
                }
                if self.project_context.branch:
                    project_dict["branch"] = self.project_context.branch

            return await self.context_builder.build(
                conversation_id=self.conversation_id,
                current_query=current_query,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                include_rag=self.config.enable_rag,
                rag_top_k=self.config.rag_top_k,
                rag_min_similarity=self.config.rag_min_similarity,
                project_context=project_dict,
            )

        # Fallback: simple context building without RAG
        messages = []

        # Add system message with project context
        system_content = system_prompt
        if self.project_context:
            system_content += f"\n\n## Current Project\n{self.project_context.to_prompt()}"

        messages.append(Message(role=MessageRole.SYSTEM, content=system_content))

        # Add recent history
        recent = self._messages_cache[-self.config.max_history_messages:]
        messages.extend(recent)

        # Add current query
        messages.append(Message(role=MessageRole.USER, content=current_query))

        return messages

    async def get_context_for_api(
        self,
        current_query: str,
        system_prompt: str,
    ) -> List[Dict[str, Any]]:
        """
        Get context formatted for API calls (dict format).

        Returns messages as list of dicts ready for OpenAI/Anthropic API.
        """
        messages = await self.build_context(current_query, system_prompt)

        return [
            {"role": msg.role.value, "content": msg.content}
            for msg in messages
        ]

    async def search_history(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[SearchResult]:
        """
        Search past conversations for relevant context.

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            Relevant past messages
        """
        if not self.vector_store:
            return []

        return await self.vector_store.search(
            query=query,
            top_k=top_k,
            min_similarity=self.config.rag_min_similarity,
        )

    async def list_sessions(
        self,
        project_path: Optional[str] = None,
        limit: int = 20,
    ) -> List[ConversationInfo]:
        """List available sessions."""
        return await self.memory.list_conversations(
            project_path=project_path,
            limit=limit,
        )

    async def switch_session(self, conversation_id: str) -> bool:
        """
        Switch to a different session.

        Args:
            conversation_id: Session to switch to

        Returns:
            True if successful
        """
        # Verify session exists
        sessions = await self.memory.list_conversations(limit=100)
        if not any(s.id == conversation_id for s in sessions):
            return False

        self.conversation_id = conversation_id
        self._messages_cache = await self._load_messages()

        # Get project path from session
        for s in sessions:
            if s.id == conversation_id and s.project_path:
                self.project_context = await self._detect_project_context(s.project_path)
                break

        return True

    async def _load_messages(self) -> List[Message]:
        """Load messages for current session."""
        if not self.conversation_id:
            return []

        stored = await self.memory.get_messages(
            self.conversation_id,
            limit=self.config.max_history_messages,
        )

        return [s.to_message() for s in stored]

    async def get_session_info(self) -> Optional[ConversationInfo]:
        """Get info about current session."""
        if not self.conversation_id:
            return None

        sessions = await self.memory.list_conversations(limit=100)
        for s in sessions:
            if s.id == self.conversation_id:
                return s
        return None

    async def clear_session(self) -> None:
        """Clear current session history (keeps session, clears messages)."""
        if self.conversation_id:
            # We don't have a delete method, so just start fresh
            self._messages_cache = []

    @property
    def message_count(self) -> int:
        """Number of messages in current session."""
        return len(self._messages_cache)

    @property
    def is_active(self) -> bool:
        """Whether a session is active."""
        return self.conversation_id is not None


# Singleton for easy access
_default_session: Optional[SessionManager] = None


def get_session_manager(config: Optional[SessionConfig] = None) -> SessionManager:
    """Get or create the default session manager."""
    global _default_session
    if _default_session is None:
        _default_session = SessionManager(config)
    return _default_session
