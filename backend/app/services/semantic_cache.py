"""
Semantic Cache Service
======================
Uses sentence embeddings to find semantically similar queries and return cached SQL,
avoiding redundant LLM calls. Since embeddings are L2-normalized, similarity is computed via dot-product.
"""

from __future__ import annotations

import json
from typing import Optional

import numpy as np
import structlog
from redis.asyncio import Redis

from app.services.embedding_service import EmbeddingService

log = structlog.get_logger(__name__)


class SemanticCache:
    """Redis-backed Semantic Query Cache using Sentence Transformers."""

    def __init__(
        self, redis_client: Optional[Redis] = None, threshold: float = 0.92
    ) -> None:
        self.redis = redis_client
        self.threshold = threshold
        self.embedder = EmbeddingService()
        self.redis_key = "copilot:semantic_cache"
        self.max_cache_size = 500

    async def get(self, question: str) -> Optional[str]:
        """
        Check if a semantically similar question exists in cache.
        Returns the cached SQL query if similarity is above threshold.
        """
        if not self.redis:
            return None

        try:
            # 1. Fetch cache index
            raw_data = await self.redis.get(self.redis_key)
            if not raw_data:
                return None

            entries = json.loads(raw_data)
            if not entries:
                return None

            # 2. Embed new question
            q_emb = np.array(
                await self.embedder.encode_single_async(question, normalize=True)
            )

            # 3. Calculate similarity (dot product of normalized vectors)
            best_score = -1.0
            best_sql = None
            best_match = None

            for entry in entries:
                cached_emb = np.array(entry["embedding"])
                similarity = float(np.dot(q_emb, cached_emb))

                if similarity > best_score:
                    best_score = similarity
                    best_sql = entry["sql"]
                    best_match = entry["question"]

            log.info(
                "Semantic cache search completed",
                best_score=best_score,
                best_match=best_match,
                threshold=self.threshold,
            )

            if best_score >= self.threshold:
                log.info(
                    "Semantic cache HIT",
                    query=question,
                    matched_query=best_match,
                    score=best_score,
                )
                return best_sql

        except Exception as e:
            log.warning("Semantic cache lookup failed", error=str(e))

        return None

    async def set(self, question: str, sql: str) -> None:
        """Add a query-SQL pair to the semantic cache."""
        if not self.redis:
            return

        try:
            q_emb = await self.embedder.encode_single_async(question, normalize=True)

            # Fetch existing entries
            raw_data = await self.redis.get(self.redis_key)
            entries = json.loads(raw_data) if raw_data else []

            # Check if this exact question is already in cache to prevent duplicate listings
            exists = False
            for entry in entries:
                if entry["question"].strip().lower() == question.strip().lower():
                    entry["sql"] = sql  # update SQL
                    exists = True
                    break

            if not exists:
                new_entry = {"question": question, "sql": sql, "embedding": q_emb}
                entries.insert(0, new_entry)

            # Cap cache size
            if len(entries) > self.max_cache_size:
                entries = entries[: self.max_cache_size]

            await self.redis.set(self.redis_key, json.dumps(entries))
            log.info("Saved query to semantic cache", query_preview=question[:80])

        except Exception as e:
            log.warning("Failed to write to semantic cache", error=str(e))
