"""Conversation session and message schemas."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)


class SessionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: Optional[str]
    is_active: bool
    last_active_at: datetime
    created_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]
    total: int


class MessageResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    generated_sql: Optional[str]
    sql_valid: Optional[bool]
    execution_ms: Optional[int]
    row_count: Optional[int]
    chart_type: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    total: int
    session_id: uuid.UUID
