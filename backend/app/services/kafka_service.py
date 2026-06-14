import asyncio
import json

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app.config import get_settings
from app.services.realtime_analytics import RealTimeAnalyticsService

log = structlog.get_logger(__name__)
settings = get_settings()


class KafkaService:
    def __init__(self):
        self.bootstrap_servers = settings.kafka_bootstrap_servers
        self.topic = settings.kafka_events_topic
        self.producer = None
        self.consumer = None

    async def start_producer(self):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self.producer.start()
        log.info("Kafka Producer started", bootstrap_servers=self.bootstrap_servers)

    async def stop_producer(self):
        if self.producer:
            await self.producer.stop()
            log.info("Kafka Producer stopped")

    async def send_event(self, event_data: dict):
        if not self.producer:
            log.error("Kafka Producer not started")
            return
        await self.producer.send_and_wait(self.topic, event_data)

    async def start_consumer(self, db_session_maker):
        self.consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id="healthcare_copilot_group",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="latest",
        )
        await self.consumer.start()
        log.info("Kafka Consumer started", topic=self.topic)

        # Background processing loop
        asyncio.create_task(self._consume_loop(db_session_maker))

    async def _consume_loop(self, db_session_maker):
        try:
            async for msg in self.consumer:
                log.info(
                    "Consumed event",
                    key=msg.key,
                    partition=msg.partition,
                    offset=msg.offset,
                )
                event_data = msg.value

                # Process the event through RealTimeAnalyticsService
                async with db_session_maker() as db_session:
                    analytics_svc = RealTimeAnalyticsService(db_session)
                    await analytics_svc.process_event(event_data)
        except Exception as e:
            log.error("Error in Kafka consume loop", error=str(e))
        finally:
            if self.consumer:
                await self.consumer.stop()
