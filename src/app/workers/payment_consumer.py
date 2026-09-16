import asyncio
import logging
from datetime import datetime, timezone

from faststream import FastStream
from faststream.rabbit import RabbitBroker, RabbitMessage

from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.db.session import session_scope
from app.messaging.broker import (
    QUEUE_DLQ,
    RETRY_QUEUES,
    declare_topology,
    dlx_exchange,
    main_exchange,
    queue_new,
)
from app.messaging.events import PaymentCreatedEvent
from app.models.payment import Payment, PaymentStatus
from app.repositories.payment_repository import PaymentRepository
from app.webhooks.sender import WebhookDeliveryError, WebhookSender
from app.workers.gateway import PaymentGatewayEmulator

logger = logging.getLogger(__name__)

settings = get_settings()
configure_logging(settings.log_level, settings.log_json)

broker = RabbitBroker(settings.rabbitmq_url)
app = FastStream(broker)

gateway = PaymentGatewayEmulator(settings)
webhook_sender = WebhookSender(settings)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@app.after_startup
async def _setup_topology() -> None:
    # Runs after the broker has connected and the `payments.new` subscriber
    # below has bound itself, so the connection is guaranteed live here.
    await declare_topology(broker)


@broker.subscriber(queue_new, exchange=main_exchange)
async def handle_payment_created(body: dict, msg: RabbitMessage) -> None:
    event = PaymentCreatedEvent.model_validate(body)
    retry_count = int(msg.headers.get("x-retry-count", 0))

    try:
        await _process(event)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: routes ANY fault to retry/DLQ
        await _handle_failure(event, retry_count, exc)


async def _process(event: PaymentCreatedEvent) -> None:
    async with session_scope() as session:
        repo = PaymentRepository(session)
        payment = await repo.get_by_id(event.payment_id)
        if payment is None:
            raise RuntimeError(f"payment {event.payment_id} not found (outbox/DB inconsistency)")

        if payment.status == PaymentStatus.PENDING:
            result = await gateway.process()
            payment.status = PaymentStatus.SUCCEEDED if result.succeeded else PaymentStatus.FAILED
            payment.failure_reason = result.failure_reason
            payment.processed_at = _utcnow()
            await session.commit()
            await session.refresh(payment)
        else:
            logger.info("payment %s already processed (status=%s); retrying webhook only", payment.id, payment.status)

    await _deliver_webhook(payment)


async def _deliver_webhook(payment: Payment) -> None:
    payload = {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": str(payment.amount),
        "currency": payment.currency.value,
        "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
        "failure_reason": payment.failure_reason,
    }

    try:
        await webhook_sender.send(payment.webhook_url, payload)
    except WebhookDeliveryError as exc:
        await _mark_webhook_outcome(payment.id, delivered=False, error=str(exc))
        # Propagate: webhook delivery is part of "processing this message"
        # for retry purposes, so an exhausted webhook attempt goes through
        # the same message-level retry/DLQ path as a gateway fault.
        raise
    else:
        await _mark_webhook_outcome(payment.id, delivered=True, error=None)


async def _mark_webhook_outcome(payment_id, delivered: bool, error: str | None) -> None:
    async with session_scope() as session:
        repo = PaymentRepository(session)
        row = await repo.get_by_id(payment_id)
        if row is not None:
            row.webhook_delivered = delivered
            row.webhook_last_error = error
            await session.commit()


async def _handle_failure(event: PaymentCreatedEvent, retry_count: int, exc: Exception) -> None:
    logger.warning(
        "processing failed for payment %s (attempt %d/%d): %s",
        event.payment_id,
        retry_count + 1,
        settings.message_max_attempts,
        exc,
    )
    payload = event.model_dump(mode="json")

    if retry_count + 1 >= settings.message_max_attempts:
        await broker.publish(
            payload,
            exchange=dlx_exchange,
            routing_key=QUEUE_DLQ,
            headers={"x-retry-count": str(retry_count + 1), "x-last-error": str(exc)[:500]},
        )
        logger.error("payment %s exhausted %d attempts, routed to DLQ", event.payment_id, settings.message_max_attempts)
    else:
        next_queue = RETRY_QUEUES[retry_count]
        await broker.publish(
            payload,
            exchange=main_exchange,
            routing_key=next_queue,
            headers={"x-retry-count": str(retry_count + 1)},
        )
        logger.info("payment %s scheduled for retry on %s", event.payment_id, next_queue)


if __name__ == "__main__":
    asyncio.run(app.run())
