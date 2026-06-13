"""
embedding_service.py
====================
Singleton sentence-embedding service with:
  • Lazy model loading (only initialised on first use)
  • Batch encoding with progress logging
  • Thread-safe access via asyncio.Lock
  • Optional L2 normalisation (for cosine similarity in ChromaDB)
  • Typed encode() returning plain Python list[list[float]]
"""

from __future__ import annotations

import asyncio
import threading
from typing import Optional

import numpy as np
import structlog
from sentence_transformers import SentenceTransformer

from app.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

# Module-level singleton — shared across all request handlers
_model: Optional[SentenceTransformer] = None
_model_lock = threading.Lock()


def get_embedder() -> SentenceTransformer:
    """
    Thread-safe lazy loader for the SentenceTransformer model.
    Returns the cached instance on subsequent calls.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:  # double-checked locking
                log.info("Loading embedding model", model=settings.embedding_model)
                _model = SentenceTransformer(settings.embedding_model)
                log.info(
                    "Embedding model ready",
                    model=settings.embedding_model,
                    dim=_model.get_sentence_embedding_dimension(),
                )
    return _model


class EmbeddingService:
    """
    High-level embedding API.

    All public methods return plain Python list[list[float]] so they are
    directly usable as ChromaDB ``embeddings=`` arguments without conversion.
    """

    def __init__(self) -> None:
        self._embedder = get_embedder()
        self._dim: int = self._embedder.get_sentence_embedding_dimension()

    @property
    def dimension(self) -> int:
        return self._dim

    def encode_batch(
        self,
        texts: list[str],
        batch_size: int = 64,
        normalize: bool = True,
        show_progress: bool = False,
    ) -> list[list[float]]:
        """
        Encode a list of texts into embeddings.

        Args:
            texts:         Input strings to embed.
            batch_size:    Internal batch size for the transformer model.
            normalize:     If True, L2-normalise each vector (required for cosine distance).
            show_progress: Log progress for large batches.

        Returns:
            List of float vectors, one per input text.
        """
        if not texts:
            return []

        if show_progress:
            log.info("Encoding batch", count=len(texts))

        embeddings: np.ndarray = self._embedder.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )

        if show_progress:
            log.info("Batch encoded", count=len(texts), dim=embeddings.shape[1])

        return embeddings.tolist()

    def encode_single(self, text: str, normalize: bool = True) -> list[float]:
        """Encode a single string and return a 1-D float list."""
        result = self._embedder.encode(
            [text],
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )
        return result[0].tolist()

    async def encode_batch_async(
        self,
        texts: list[str],
        batch_size: int = 64,
        normalize: bool = True,
        show_progress: bool = False,
    ) -> list[list[float]]:
        """
        Runs directly on the main thread to avoid PyTorch + ThreadPoolExecutor deadlocks on Windows.
        """
        return self.encode_batch(
            texts,
            batch_size=batch_size,
            normalize=normalize,
            show_progress=show_progress,
        )

    async def encode_single_async(self, text: str, normalize: bool = True) -> list[float]:
        """Runs directly on the main thread to avoid PyTorch + ThreadPoolExecutor deadlocks on Windows."""
        return self.encode_single(text, normalize=normalize)

