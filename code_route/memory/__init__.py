"""Memory and RAG system for Code Route."""

from .sqlite import SQLiteMemory, Conversation, StoredMessage
from .embeddings import LocalEmbeddings
from .vector_store import VectorStore
from .context import ContextBuilder, ConversationManager
from .session import SessionManager, SessionConfig, ProjectContext, get_session_manager

# Alias for backwards compatibility
ConversationInfo = Conversation

__all__ = [
    # SQLite storage
    "SQLiteMemory",
    "Conversation",
    "ConversationInfo",  # Alias
    "StoredMessage",
    # Embeddings
    "LocalEmbeddings",
    # Vector store
    "VectorStore",
    # Context building
    "ContextBuilder",
    "ConversationManager",
    # Session management
    "SessionManager",
    "SessionConfig",
    "ProjectContext",
    "get_session_manager",
]
