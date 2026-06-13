"""ORM model registry — import all models so Alembic can detect them."""

from app.db.models.user import User  # noqa: F401
from app.db.models.healthcare import (
    Patient,
    Provider,
    Department,
    Facility,
    Encounter,
    Diagnosis,
    Procedure,
    Medication,
    LabResult,
    VitalSign,
    Claim,
    Readmission,
)  # noqa: F401
from app.db.models.copilot import (
    CopilotSession,
    CopilotMessage,
    NLSQLPair,
    SchemaRegistry,
)  # noqa: F401
from app.db.models.audit import AuditLog  # noqa: F401
from app.db.models.alert import Alert  # noqa: F401
