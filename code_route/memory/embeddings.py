"""Local embeddings using sentence-transformers."""

import hashlib
from pathlib import Path
from typing import List, Optional, Union
import numpy as np

# Lazy load to avoid slow import on startup
_model = None
_model_name = None


def _get_model(model_name: str):
    """Lazy load the embedding model."""
    global _model, _model_name

    if _model is None or _model_name != model_name:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(model_name)
        _model_name = model_name

    return _model


class LocalEmbeddings:
    """
    Local text embeddings using sentence-transformers.

    Uses lightweight models that run efficiently on CPU.
    No external API calls required.

    Models (by size/quality tradeoff):
    - all-MiniLM-L6-v2: 80MB, fast, good quality (default)
    - all-mpnet-base-v2: 420MB, slower, best quality
    - paraphrase-MiniLM-L3-v2: 60MB, fastest, decent quality

    Usage:
        embeddings = LocalEmbeddings()

        # Single text
        vec = embeddings.embed("Hello world")

        # Batch
        vecs = embeddings.embed_batch(["Hello", "World"])

        # Similarity
        sim = embeddings.similarity(vec1, vec2)
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        cache_dir: Optional[Path] = None,
    ):
        """
        Initialize embeddings.

        Args:
            model_name: Sentence transformer model name
            cache_dir: Directory for model cache (default: ~/.cache/torch)
        """
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._dimension: Optional[int] = None

    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        if self._dimension is None:
            # Get dimension by embedding a test string
            model = _get_model(self.model_name)
            self._dimension = model.get_sentence_embedding_dimension()
        return self._dimension

    def embed(self, text: str) -> np.ndarray:
        """
        Embed a single text string.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as numpy array
        """
        model = _get_model(self.model_name)
        return model.encode(text, convert_to_numpy=True)

    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> np.ndarray:
        """
        Embed multiple texts.

        Args:
            texts: List of texts to embed
            batch_size: Batch size for encoding
            show_progress: Show progress bar

        Returns:
            2D numpy array of shape (len(texts), dimension)
        """
        model = _get_model(self.model_name)
        return model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
        )

    def similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
    ) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Similarity score between -1 and 1
        """
        # Normalize
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(embedding1, embedding2) / (norm1 * norm2))

    def most_similar(
        self,
        query_embedding: np.ndarray,
        embeddings: np.ndarray,
        top_k: int = 5,
    ) -> List[tuple[int, float]]:
        """
        Find most similar embeddings to a query.

        Args:
            query_embedding: Query vector
            embeddings: Matrix of embeddings to search (N x D)
            top_k: Number of results to return

        Returns:
            List of (index, similarity) tuples, sorted by similarity descending
        """
        # Normalize query
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-9)

        # Normalize all embeddings
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-9
        normalized = embeddings / norms

        # Compute all similarities at once
        similarities = np.dot(normalized, query_norm)

        # Get top k indices
        if top_k >= len(similarities):
            top_indices = np.argsort(similarities)[::-1]
        else:
            top_indices = np.argpartition(similarities, -top_k)[-top_k:]
            top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]

        return [(int(idx), float(similarities[idx])) for idx in top_indices]

    def to_bytes(self, embedding: np.ndarray) -> bytes:
        """Convert embedding to bytes for storage."""
        return embedding.astype(np.float32).tobytes()

    def from_bytes(self, data: bytes) -> np.ndarray:
        """Convert bytes back to embedding."""
        return np.frombuffer(data, dtype=np.float32)


class TextChunker:
    """
    Split text into chunks for embedding.

    Handles long texts by splitting into overlapping chunks
    that fit within the embedding model's context window.
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separator: str = "\n",
    ):
        """
        Initialize chunker.

        Args:
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between chunks
            separator: Preferred split point
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separator = separator

    def chunk(self, text: str) -> List[str]:
        """
        Split text into chunks.

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            # If not at the end, try to break at separator
            if end < len(text):
                # Look for separator near the end
                break_point = text.rfind(self.separator, start + self.chunk_size // 2, end)
                if break_point != -1:
                    end = break_point + len(self.separator)

            chunks.append(text[start:end].strip())

            # Move start, accounting for overlap
            start = end - self.chunk_overlap

            # Avoid tiny final chunks
            if len(text) - start < self.chunk_size // 4:
                if chunks:
                    # Append remaining to last chunk
                    chunks[-1] = chunks[-1] + " " + text[start:].strip()
                break

        return [c for c in chunks if c]  # Filter empty

    def chunk_with_metadata(
        self,
        text: str,
        source: Optional[str] = None,
    ) -> List[dict]:
        """
        Split text into chunks with metadata.

        Args:
            text: Text to split
            source: Optional source identifier

        Returns:
            List of dicts with 'text', 'index', 'source' keys
        """
        chunks = self.chunk(text)
        return [
            {
                "text": chunk,
                "index": i,
                "source": source,
                "char_start": sum(len(c) for c in chunks[:i]),
            }
            for i, chunk in enumerate(chunks)
        ]
