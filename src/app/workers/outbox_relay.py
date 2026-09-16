"""
Standalone worker: polls the outbox table and publishes pending events to
RabbitMQ, marking each row published once the broker has confirmed it.
"""

import asyncio
import logging

from faststream.rabbit import RabbitBroker

from app.core.config import Settings, get_settings
from app.core.logging_config import configure_logging
from app.db.session import session_scope
from app.messaging.broker import QUEUE_NEW, declare_topology, main_exchange
from app.models.outbox import OutboxStatus
from app.repositories.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)


async def relay_once(broker: RabbitBroker, settings: Settings) -> int:
    """Publish one batch of pending outbox events. Returns how many were published."""
    async with session_scope() as session:
        repo = OutboxRepository(session)
        events = await repo.lock_pending_batch(settings.outbox_batch_size)
        if not events:
            return 0

        published = 0
        for event in events:
            try:
                await broker.publish(
                    event.payload,
                    exchange=main_exchange,
                    routing_key=QUEUE_NEW,
                    headers={"x-retry-count": "0"},
                )
            except Exception:
                logger.exception("failed to publish outbox event id=%s", event.id)
                event.attempts += 1
                event.last_error = "publish failed, will retry next poll"
                if event.attempts >= 10:
                    event.status = OutboxStatus.FAILED
            else:
                event.status = OutboxStatus.PUBLISHED
                event.published_at = _utcnow()
                published += 1

        await session.commit()
        return published


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


async def run_forever() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    broker = RabbitBroker(settings.rabbitmq_url)
    await broker.connect()
    await declare_topology(broker)

    logger.info("outbox relay started, polling every %.1fs", settings.outbox_poll_interval_seconds)
    try:
        while True:
            try:
                count = await relay_once(broker, settings)
                if count:
                    logger.info("published %d outbox event(s)", count)
            except Exception:
                logger.exception("outbox relay iteration failed")
            await asyncio.sleep(settings.outbox_poll_interval_seconds)
    finally:
        await broker.stop()


if __name__ == "__main__":
    asyncio.run(run_forever())
