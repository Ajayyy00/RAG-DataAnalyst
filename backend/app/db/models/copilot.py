"""Copilot system ORM models: sessions, messages, NL-SQL pairs, schema registry."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class CopilotSession(Base):
    """A conversation session between a user and the copilot."""

    __tablename__ = "copilot_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="sessions")
    messages: Mapped[List["CopilotMessage"]] = relationship(
        "CopilotMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CopilotMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<CopilotSession id={self.id} user_id={self.user_id}>"


class CopilotMessage(Base):
    """A single message turn within a copilot session."""

    __tablename__ = "copilot_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("copilot_sessions.id"), nullable=False, index=True
    )
    # role: user | assistant | system
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str | None] = mapped_column(Text)
    sql_valid: Mapped[bool | None] = mapped_column(Boolean)
    execution_ms: Mapped[int | None] = mapped_column(Integer)
    row_count: Mapped[int | None] = mapped_column(Integer)
    chart_type: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    session: Mapped["CopilotSession"] = relationship("CopilotSession", back_populates="messages")
    nl_sql_pair: Mapped[Optional["NLSQLPair"]] = relationship(
        "NLSQLPair", back_populates="message", uselist=False
    )

    def __repr__(self) -> str:
        return f"<CopilotMessage id={self.id} role={self.role}>"


class NLSQLPair(Base):
    """Captures NL→SQL pairs for fine-tuning dataset construction."""

    __tablename__ = "nl_sql_pairs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("copilot_messages.id"))
    nl_question: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_sql: Mapped[str | None] = mapped_column(Text)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)  # Thumbs up/down
    difficulty: Mapped[str | None] = mapped_column(String(20))  # simple | medium | complex
    query_type: Mapped[str | None] = mapped_column(String(50))  # aggregation | filter | join | window
    schema_version: Mapped[str | None] = mapped_column(String(20))
    split: Mapped[str] = mapped_column(String(10), default="train")  # train | val | test
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    message: Mapped[Optional["CopilotMessage"]] = relationship(
        "CopilotMessage", back_populates="nl_sql_pair"
    )


class SchemaRegistry(Base):
    """Tracks known tables/columns for SQL validation."""

    __tablename__ = "schema_registry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    column_name: Mapped[str] = mapped_column(String(100), nullable=False)
    data_type: Mapped[str | None] = mapped_column(String(50))
    is_nullable: Mapped[bool | None] = mapped_column(Boolean)
    column_comment: Mapped[str | None] = mapped_column(Text)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
