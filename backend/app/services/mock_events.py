import asyncio
import random
import uuid
import datetime
import structlog

from app.services.kafka_service import KafkaService

log = structlog.get_logger(__name__)

async def run_mock_event_generator():
    """Generates synthetic clinical events and publishes them to Kafka."""
    kafka_svc = KafkaService()
    
    # Wait a bit for the system to start
    await asyncio.sleep(5)
    
    try:
        await kafka_svc.start_producer()
    except Exception as e:
        log.warning("Mock Generator: Failed to start Kafka producer (is Kafka running?)", error=str(e))
        return

    log.info("Mock Event Generator started")
    
    try:
        while True:
            # Generate a synthetic vital sign event
            heart_rate = random.randint(60, 150)
            patient_id = str(uuid.uuid4())
            
            event = {
                "event_id": str(uuid.uuid4()),
                "patient_id": patient_id,
                "event_type": "vital_sign",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "data": {
                    "heart_rate": heart_rate,
                    "blood_pressure_systolic": random.randint(100, 180),
                    "blood_pressure_diastolic": random.randint(60, 110)
                }
            }
            
            await kafka_svc.send_event(event)
            log.info("Mock Generator: Published event", heart_rate=heart_rate)
            
            # Send an event every 5 seconds
            await asyncio.sleep(5)
            
    except asyncio.CancelledError:
        log.info("Mock Event Generator cancelled")
    except Exception as e:
        log.error("Mock Event Generator failed", error=str(e))
    finally:
        await kafka_svc.stop_producer()
