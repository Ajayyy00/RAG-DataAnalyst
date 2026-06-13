import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class AlertBase(BaseModel):
    event_type: str
    severity: str
    message: str
    metadata_json: Optional[Dict[str, Any]] = None
    resolved: bool = False

class AlertCreate(AlertBase):
    pass

class AlertRead(AlertBase):
    id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True

class ClinicalEvent(BaseModel):
    """Schema for incoming Kafka clinical events."""
    event_id: str
    patient_id: str
    event_type: str  # e.g. "vital_sign", "admission", "lab_result"
    timestamp: str
    data: Dict[str, Any]
