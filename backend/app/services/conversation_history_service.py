"""Conversation history service: persists messages in PostgreSQL and caches in Redis."""

import json
import uuid
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.models.copilot import CopilotMessage, CopilotSession

logger = structlog.get_logger(__name__)
settings = get_settings()

SESSION_CACHE_PREFIX = "session:"
HISTORY_CACHE_PREFIX = "history:"


class ConversationHistoryService:
    """Manages session creation, message storage, and Redis-backed history caching."""

    def __init__(self, db: AsyncSession, redis: aioredis.Redis) -> None:
        self.db = db
        self.redis = redis

    # ── Session Management ────────────────────────────────────

    async def create_session(
        self, user_id: uuid.UUID, title: Optional[str] = None
    ) -> CopilotSession:
        """Create a new conversation session."""
        session = CopilotSession(user_id=user_id, title=title)
        self.db.add(session)
        await self.db.flush()
        logger.info("Session created", session_id=str(session.id), user_id=str(user_id))
        return session

    async def get_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> CopilotSession:
        """Fetch a session by ID, validating ownership."""
        result = await self.db.execute(
            select(CopilotSession).where(
                CopilotSession.id == session_id,
                CopilotSession.user_id == user_id,
                CopilotSession.is_active.is_(True),
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise NotFoundError("Session")
        return session

    async def list_sessions(
        self, user_id: uuid.UUID, limit: int = 50
    ) -> List[CopilotSession]:
        """List active sessions for a user, most recent first."""
        result = await self.db.execute(
            select(CopilotSession)
            .where(
                CopilotSession.user_id == user_id, CopilotSession.is_active.is_(True)
            )
            .order_by(CopilotSession.last_active_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def archive_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Soft-delete a session."""
        session = await self.get_session(session_id, user_id)
        session.is_active = False
        await self.redis.delete(f"{HISTORY_CACHE_PREFIX}{session_id}")
        logger.info("Session archived", session_id=str(session_id))

    # ── Message Management ────────────────────────────────────

    async def save_message(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        generated_sql: Optional[str] = None,
        sql_valid: Optional[bool] = None,
        execution_ms: Optional[int] = None,
        row_count: Optional[int] = None,
        chart_type: Optional[str] = None,
    ) -> CopilotMessage:
        """Persist a message to PostgreSQL and invalidate the session cache."""
        message = CopilotMessage(
            session_id=session_id,
            role=role,
            content=content,
            generated_sql=generated_sql,
            sql_valid=sql_valid,
            execution_ms=execution_ms,
            row_count=row_count,
            chart_type=chart_type,
        )
        self.db.add(message)
        await self.db.flush()

        # Invalidate Redis cache so next history call re-reads from DB
        await self.redis.delete(f"{HISTORY_CACHE_PREFIX}{session_id}")
        return message

    async def get_messages(
        self, session_id: uuid.UUID, limit: int = 50
    ) -> List[CopilotMessage]:
        """Fetch messages for a session, ordered chronologically."""
        result = await self.db.execute(
            select(CopilotMessage)
            .where(CopilotMessage.session_id == session_id)
            .order_by(CopilotMessage.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_conversation_context(
        self, session_id: uuid.UUID, max_turns: int = 6
    ) -> List[Dict[str, str]]:
        """
        Return the last N message turns in OpenAI chat format
        [{role, content}, ...], suitable for LLM context injection.
        Uses Redis cache for speed.
        """
        cache_key = f"{HISTORY_CACHE_PREFIX}{session_id}"
        cached = await self.redis.get(cache_key)
        if cached:
            all_messages: List[Dict[str, str]] = json.loads(cached)
            return all_messages[-(max_turns * 2) :]

        messages = await self.get_messages(session_id, limit=100)
        formatted = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]

        # Cache for session TTL
        await self.redis.setex(
            cache_key,
            settings.session_ttl_seconds,
            json.dumps(formatted),
        )
        return formatted[-(max_turns * 2) :]
