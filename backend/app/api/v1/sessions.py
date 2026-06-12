"""Session management routes: CRUD for conversation sessions and message history."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query, status

from app.dependencies import CurrentUser, DbSession, RedisClient
from app.schemas.session import (
    MessageListResponse,
    MessageResponse,
    SessionCreateRequest,
    SessionListResponse,
    SessionResponse,
)
from app.services.conversation_history_service import ConversationHistoryService

router = APIRouter()


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation session",
)
async def create_session(
    data: SessionCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
) -> SessionResponse:
    svc = ConversationHistoryService(db, redis)
    session = await svc.create_session(current_user.id, data.title)
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        is_active=session.is_active,
        last_active_at=session.last_active_at,
        created_at=session.created_at,
        message_count=0,
    )


@router.get(
    "",
    response_model=SessionListResponse,
    summary="List all sessions for the current user",
)
async def list_sessions(
    current_user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    limit: int = Query(default=50, le=100),
) -> SessionListResponse:
    svc = ConversationHistoryService(db, redis)
    sessions = await svc.list_sessions(current_user.id, limit=limit)
    session_responses = [
        SessionResponse(
            id=s.id,
            user_id=s.user_id,
            title=s.title,
            is_active=s.is_active,
            last_active_at=s.last_active_at,
            created_at=s.created_at,
        )
        for s in sessions
    ]
    return SessionListResponse(sessions=session_responses, total=len(session_responses))


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Get a session by ID",
)
async def get_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
) -> SessionResponse:
    svc = ConversationHistoryService(db, redis)
    session = await svc.get_session(session_id, current_user.id)
    messages = await svc.get_messages(session_id)
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        is_active=session.is_active,
        last_active_at=session.last_active_at,
        created_at=session.created_at,
        message_count=len(messages),
    )


@router.get(
    "/{session_id}/messages",
    response_model=MessageListResponse,
    summary="Get all messages in a session",
)
async def get_session_messages(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    limit: int = Query(default=100, le=500),
) -> MessageListResponse:
    svc = ConversationHistoryService(db, redis)
    await svc.get_session(session_id, current_user.id)  # verify ownership
    messages = await svc.get_messages(session_id, limit=limit)
    return MessageListResponse(
        messages=[MessageResponse.model_validate(m) for m in messages],
        total=len(messages),
        session_id=session_id,
    )


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive (soft-delete) a session",
)
async def archive_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
) -> None:
    svc = ConversationHistoryService(db, redis)
    await svc.archive_session(session_id, current_user.id)
