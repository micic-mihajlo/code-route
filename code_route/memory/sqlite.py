"""SQLite-based conversation storage for Code Route."""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.types import Message, MessageRole


@dataclass
class StoredMessage:
    """A message stored in the database."""
    id: int
    conversation_id: str
    role: str
    content: str
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_message(self) -> Message:
        """Convert to Message object."""
        from ..core.types import ToolCall

        tool_calls = None
        if self.tool_calls:
            tool_calls = [
                ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
                for tc in self.tool_calls
            ]

        return Message(
            role=MessageRole(self.role),
            content=self.content,
            tool_calls=tool_calls,
            tool_call_id=self.tool_call_id,
        )


@dataclass
class Conversation:
    """A conversation with metadata."""
    id: str
    created_at: datetime
    updated_at: datetime
    project_path: Optional[str] = None
    title: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    message_count: int = 0


class SQLiteMemory:
    """
    SQLite-based storage for conversations and messages.

    Provides:
    - Conversation persistence across sessions
    - Message history retrieval
    - Search by project path
    - Metadata storage

    Usage:
        memory = SQLiteMemory()

        # Create conversation
        conv_id = await memory.create_conversation(project_path="/my/project")

        # Save messages
        await memory.save_message(conv_id, Message(role="user", content="Hello"))

        # Retrieve history
        messages = await memory.get_messages(conv_id)
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize SQLite memory.

        Args:
            db_path: Path to SQLite database. Defaults to ~/.code_route/memory.db
        """
        if db_path is None:
            db_path = Path.home() / ".code_route" / "memory.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.executescript("""
                -- Conversations table
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    project_path TEXT,
                    title TEXT,
                    metadata TEXT DEFAULT '{}'
                );

                -- Messages table
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls TEXT,
                    tool_call_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Embeddings table (for vector search)
                CREATE TABLE IF NOT EXISTS embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
                    message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
                    chunk_index INTEGER DEFAULT 0,
                    chunk_text TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Indexes
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_created
                    ON messages(created_at);
                CREATE INDEX IF NOT EXISTS idx_conversations_project
                    ON conversations(project_path);
                CREATE INDEX IF NOT EXISTS idx_conversations_updated
                    ON conversations(updated_at);
                CREATE INDEX IF NOT EXISTS idx_embeddings_conversation
                    ON embeddings(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_embeddings_message
                    ON embeddings(message_id);
            """)
            conn.commit()

    async def create_conversation(
        self,
        project_path: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a new conversation.

        Args:
            project_path: Path to the project this conversation is about
            title: Optional title for the conversation
            metadata: Additional metadata to store

        Returns:
            Conversation ID
        """
        conv_id = str(uuid.uuid4())
        metadata_json = json.dumps(metadata or {})

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, project_path, title, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (conv_id, project_path, title, metadata_json)
            )
            conn.commit()

        return conv_id

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get a conversation by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT c.*, COUNT(m.id) as message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.id = ?
                GROUP BY c.id
                """,
                (conversation_id,)
            ).fetchone()

            if not row:
                return None

            return Conversation(
                id=row["id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                project_path=row["project_path"],
                title=row["title"],
                metadata=json.loads(row["metadata"] or "{}"),
                message_count=row["message_count"],
            )

    async def list_conversations(
        self,
        project_path: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Conversation]:
        """
        List conversations, optionally filtered by project.

        Args:
            project_path: Filter by project path
            limit: Maximum number to return
            offset: Number to skip

        Returns:
            List of conversations, most recent first
        """
        with self._get_connection() as conn:
            if project_path:
                rows = conn.execute(
                    """
                    SELECT c.*, COUNT(m.id) as message_count
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    WHERE c.project_path = ?
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (project_path, limit, offset)
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT c.*, COUNT(m.id) as message_count
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset)
                ).fetchall()

            return [
                Conversation(
                    id=row["id"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                    project_path=row["project_path"],
                    title=row["title"],
                    metadata=json.loads(row["metadata"] or "{}"),
                    message_count=row["message_count"],
                )
                for row in rows
            ]

    async def save_message(
        self,
        conversation_id: str,
        message: Message,
    ) -> int:
        """
        Save a message to a conversation.

        Args:
            conversation_id: The conversation to add to
            message: The message to save

        Returns:
            Message ID
        """
        tool_calls_json = None
        if message.tool_calls:
            tool_calls_json = json.dumps([
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in message.tool_calls
            ])

        content = message.content if isinstance(message.content, str) else json.dumps(message.content)

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, tool_calls, tool_call_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversation_id, message.role.value, content, tool_calls_json, message.tool_call_id)
            )

            # Update conversation timestamp
            conn.execute(
                "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (conversation_id,)
            )

            conn.commit()
            return cursor.lastrowid

    async def get_messages(
        self,
        conversation_id: str,
        limit: Optional[int] = None,
        before_id: Optional[int] = None,
    ) -> List[StoredMessage]:
        """
        Get messages from a conversation.

        Args:
            conversation_id: The conversation to get messages from
            limit: Maximum number of messages
            before_id: Get messages before this ID (for pagination)

        Returns:
            List of messages, oldest first
        """
        with self._get_connection() as conn:
            query = "SELECT * FROM messages WHERE conversation_id = ?"
            params: List[Any] = [conversation_id]

            if before_id:
                query += " AND id < ?"
                params.append(before_id)

            query += " ORDER BY id ASC"

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            rows = conn.execute(query, params).fetchall()

            return [
                StoredMessage(
                    id=row["id"],
                    conversation_id=row["conversation_id"],
                    role=row["role"],
                    content=row["content"],
                    tool_calls=json.loads(row["tool_calls"]) if row["tool_calls"] else None,
                    tool_call_id=row["tool_call_id"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    async def get_recent_messages(
        self,
        conversation_id: str,
        limit: int = 20,
    ) -> List[Message]:
        """
        Get recent messages as Message objects.

        Args:
            conversation_id: The conversation
            limit: Number of recent messages

        Returns:
            List of Message objects, oldest first
        """
        stored = await self.get_messages(conversation_id, limit=limit)
        return [msg.to_message() for msg in stored]

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its messages."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    async def search_conversations(
        self,
        query: str,
        project_path: Optional[str] = None,
        limit: int = 20,
    ) -> List[Conversation]:
        """
        Search conversations by message content.

        Args:
            query: Text to search for
            project_path: Optional project filter
            limit: Maximum results

        Returns:
            Matching conversations
        """
        with self._get_connection() as conn:
            if project_path:
                rows = conn.execute(
                    """
                    SELECT DISTINCT c.*, COUNT(m.id) as message_count
                    FROM conversations c
                    JOIN messages m ON m.conversation_id = c.id
                    WHERE m.content LIKE ? AND c.project_path = ?
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT ?
                    """,
                    (f"%{query}%", project_path, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT DISTINCT c.*, COUNT(m.id) as message_count
                    FROM conversations c
                    JOIN messages m ON m.conversation_id = c.id
                    WHERE m.content LIKE ?
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT ?
                    """,
                    (f"%{query}%", limit)
                ).fetchall()

            return [
                Conversation(
                    id=row["id"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                    project_path=row["project_path"],
                    title=row["title"],
                    metadata=json.loads(row["metadata"] or "{}"),
                    message_count=row["message_count"],
                )
                for row in rows
            ]

    async def update_conversation_title(
        self,
        conversation_id: str,
        title: str,
    ) -> bool:
        """Update conversation title."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (title, conversation_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    async def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        with self._get_connection() as conn:
            conv_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            embed_count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]

            return {
                "conversations": conv_count,
                "messages": msg_count,
                "embeddings": embed_count,
                "db_path": str(self.db_path),
                "db_size_mb": round(self.db_path.stat().st_size / (1024 * 1024), 2) if self.db_path.exists() else 0,
            }
