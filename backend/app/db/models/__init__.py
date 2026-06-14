"""ORM model registry — import all models so Alembic can detect them."""

from app.db.models.alert import Alert  # noqa: F401
from app.db.models.audit import AuditLog  # noqa: F401
from app.db.models.copilot import CopilotMessage  # noqa: F401
from app.db.models.copilot import CopilotSession, NLSQLPair, SchemaRegistry
from app.db.models.healthcare import Department  # noqa: F401
from app.db.models.healthcare import (
    Claim,
    Diagnosis,
    Encounter,
    Facility,
    LabResult,
    Medication,
    Patient,
    Procedure,
    Provider,
    Readmission,
    VitalSign,
)
from app.db.models.user import User  # noqa: F401
