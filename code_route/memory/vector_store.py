"""Vector store for semantic search using SQLite."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from .embeddings import LocalEmbeddings, TextChunker


@dataclass
class SearchResult:
    """Result from vector search."""
    text: str
    similarity: float
    conversation_id: Optional[str] = None
    message_id: Optional[int] = None
    chunk_index: int = 0
    metadata: Optional[Dict[str, Any]] = None


class VectorStore:
    """
    Vector store for semantic similarity search.

    Uses SQLite for storage with in-memory similarity computation.
    Suitable for small-medium datasets (up to ~100k vectors).

    For larger datasets, consider using a dedicated vector DB.

    Usage:
        store = VectorStore()

        # Add texts
        store.add_texts(["Hello world", "Goodbye world"], conversation_id="abc")

        # Search
        results = store.search("greeting", top_k=5)
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        embeddings: Optional[LocalEmbeddings] = None,
        chunker: Optional[TextChunker] = None,
    ):
        """
        Initialize vector store.

        Args:
            db_path: Path to SQLite database (uses memory DB's embeddings table)
            embeddings: Embeddings model to use
            chunker: Text chunker for long texts
        """
        if db_path is None:
            db_path = Path.home() / ".code_route" / "memory.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.embeddings = embeddings or LocalEmbeddings()
        self.chunker = chunker or TextChunker()

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Ensure embeddings table exists."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT,
                    message_id INTEGER,
                    chunk_index INTEGER DEFAULT 0,
                    chunk_text TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_conversation
                ON embeddings(conversation_id)
            """)
            conn.commit()

    async def add_text(
        self,
        text: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[int]:
        """
        Add a text to the store.

        Long texts are automatically chunked.

        Args:
            text: Text to add
            conversation_id: Associated conversation
            message_id: Associated message
            metadata: Additional metadata

        Returns:
            List of embedding IDs created
        """
        chunks = self.chunker.chunk(text)
        return await self.add_chunks(
            chunks,
            conversation_id=conversation_id,
            message_id=message_id,
            metadata=metadata,
        )

    async def add_chunks(
        self,
        chunks: List[str],
        conversation_id: Optional[str] = None,
        message_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[int]:
        """
        Add pre-chunked texts to the store.

        Args:
            chunks: List of text chunks
            conversation_id: Associated conversation
            message_id: Associated message
            metadata: Additional metadata

        Returns:
            List of embedding IDs created
        """
        if not chunks:
            return []

        # Generate embeddings
        vectors = self.embeddings.embed_batch(chunks)

        import json
        metadata_json = json.dumps(metadata) if metadata else None

        ids = []
        with self._get_connection() as conn:
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                cursor = conn.execute(
                    """
                    INSERT INTO embeddings
                    (conversation_id, message_id, chunk_index, chunk_text, embedding, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conversation_id,
                        message_id,
                        i,
                        chunk,
                        self.embeddings.to_bytes(vector),
                        metadata_json,
                    )
                )
                ids.append(cursor.lastrowid)
            conn.commit()

        return ids

    async def search(
        self,
        query: str,
        top_k: int = 5,
        conversation_id: Optional[str] = None,
        min_similarity: float = 0.0,
    ) -> List[SearchResult]:
        """
        Search for similar texts.

        Args:
            query: Search query
            top_k: Number of results
            conversation_id: Filter by conversation
            min_similarity: Minimum similarity threshold

        Returns:
            List of search results sorted by similarity
        """
        # Embed query
        query_vector = self.embeddings.embed(query)

        # Load candidates from database
        with self._get_connection() as conn:
            if conversation_id:
                rows = conn.execute(
                    "SELECT * FROM embeddings WHERE conversation_id = ?",
                    (conversation_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM embeddings").fetchall()

        if not rows:
            return []

        # Compute similarities
        import json
        results = []
        for row in rows:
            vector = self.embeddings.from_bytes(row["embedding"])
            similarity = self.embeddings.similarity(query_vector, vector)

            if similarity >= min_similarity:
                results.append(SearchResult(
                    text=row["chunk_text"],
                    similarity=similarity,
                    conversation_id=row["conversation_id"],
                    message_id=row["message_id"],
                    chunk_index=row["chunk_index"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else None,
                ))

        # Sort and limit
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:top_k]

    async def search_in_conversations(
        self,
        query: str,
        conversation_ids: List[str],
        top_k: int = 5,
    ) -> List[SearchResult]:
        """
        Search within specific conversations.

        Args:
            query: Search query
            conversation_ids: Conversations to search
            top_k: Number of results

        Returns:
            List of search results
        """
        query_vector = self.embeddings.embed(query)

        placeholders = ",".join("?" * len(conversation_ids))
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM embeddings WHERE conversation_id IN ({placeholders})",
                conversation_ids
            ).fetchall()

        if not rows:
            return []

        import json
        results = []
        for row in rows:
            vector = self.embeddings.from_bytes(row["embedding"])
            similarity = self.embeddings.similarity(query_vector, vector)

            results.append(SearchResult(
                text=row["chunk_text"],
                similarity=similarity,
                conversation_id=row["conversation_id"],
                message_id=row["message_id"],
                chunk_index=row["chunk_index"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else None,
            ))

        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:top_k]

    async def delete_by_conversation(self, conversation_id: str) -> int:
        """Delete all embeddings for a conversation."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM embeddings WHERE conversation_id = ?",
                (conversation_id,)
            )
            conn.commit()
            return cursor.rowcount

    async def delete_by_message(self, message_id: int) -> int:
        """Delete all embeddings for a message."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM embeddings WHERE message_id = ?",
                (message_id,)
            )
            conn.commit()
            return cursor.rowcount

    async def get_stats(self) -> Dict[str, Any]:
        """Get vector store statistics."""
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
            conversations = conn.execute(
                "SELECT COUNT(DISTINCT conversation_id) FROM embeddings"
            ).fetchone()[0]

        return {
            "total_embeddings": total,
            "conversations_with_embeddings": conversations,
            "embedding_dimension": self.embeddings.dimension,
            "model": self.embeddings.model_name,
        }
