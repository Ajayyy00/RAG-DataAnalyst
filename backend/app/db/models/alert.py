import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String, index=True, nullable=False)
    severity = Column(
        String, index=True, nullable=False
    )  # e.g., info, warning, critical
    message = Column(String, nullable=False)
    metadata_json = Column(
        JSON, nullable=True
    )  # Renamed from metadata to avoid SQLAlchemy conflicts
    resolved = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
