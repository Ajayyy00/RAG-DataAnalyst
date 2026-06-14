import json

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

# We will import the websocket manager dynamically to avoid circular imports
from app.api.v1.websockets import manager
from app.db.models.alert import Alert
from app.schemas.alert import ClinicalEvent

log = structlog.get_logger(__name__)


class RealTimeAnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        # We assume get_redis() works synchronously or we can await it
        # Actually it's better to just get it from the app state or inject it.
        # But we can use the global Redis dependency if needed.

    async def process_event(self, event_dict: dict):
        """Evaluate clinical event against alert rules."""
        try:
            event = ClinicalEvent(**event_dict)
            log.info(
                "Processing realtime event",
                event_type=event.event_type,
                patient_id=event.patient_id,
            )

            # Rule 1: High Heart Rate
            if event.event_type == "vital_sign" and "heart_rate" in event.data:
                hr = event.data["heart_rate"]
                if hr > 120:
                    await self._trigger_alert(
                        event_type="vital_sign_alert",
                        severity="critical",
                        message=f"Critical High Heart Rate: {hr} bpm",
                        metadata={"patient_id": event.patient_id, "heart_rate": hr},
                    )

            # Additional processing/aggregations could be done here in Redis
            # e.g., incrementing live dashboard stats

            # Broadcast the live event to any dashboards listening
            await manager.broadcast_event(
                {"type": "live_event", "data": event.model_dump()}
            )

        except Exception as e:
            log.error(
                "Failed to process realtime event", error=str(e), event=event_dict
            )

    async def _trigger_alert(
        self, event_type: str, severity: str, message: str, metadata: dict
    ):
        """Create an alert in postgres and broadcast it."""
        alert = Alert(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata_json=metadata,
        )
        self.db.add(alert)
        await self.db.commit()
        await self.db.refresh(alert)

        # Broadcast the alert via WebSockets
        alert_payload = {
            "type": "new_alert",
            "data": {
                "id": str(alert.id),
                "event_type": alert.event_type,
                "severity": alert.severity,
                "message": alert.message,
                "metadata": alert.metadata_json,
                "created_at": alert.created_at.isoformat(),
            },
        }
        await manager.broadcast_event(alert_payload)
        log.info(
            "Alert triggered and broadcasted", alert_id=str(alert.id), severity=severity
        )
