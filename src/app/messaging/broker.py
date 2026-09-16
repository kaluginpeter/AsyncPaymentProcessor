"""
    payments.new  --(handler raises)--> payments.retry.1 (TTL 2s) --> payments.new
    payments.new  --(handler raises)--> payments.retry.2 (TTL 4s) --> payments.new
    payments.new  --(3rd failure)-----> payments.new.dlq  (terminal)

Attempt count travels in the message header `x-retry-count`, set explicitly
by the consumer.
"""

from typing import TYPE_CHECKING

from faststream.rabbit import ExchangeType, RabbitExchange, RabbitQueue

from app.core.config import get_settings

if TYPE_CHECKING:
    from faststream.rabbit import RabbitBroker

MAIN_EXCHANGE_NAME = "payments.exchange"
DLX_EXCHANGE_NAME = "payments.dlx"

QUEUE_NEW = "payments.new"
QUEUE_RETRY_1 = "payments.retry.1"
QUEUE_RETRY_2 = "payments.retry.2"
QUEUE_DLQ = "payments.new.dlq"

RETRY_QUEUES = (QUEUE_RETRY_1, QUEUE_RETRY_2)

main_exchange = RabbitExchange(MAIN_EXCHANGE_NAME, type=ExchangeType.DIRECT, durable=True)
dlx_exchange = RabbitExchange(DLX_EXCHANGE_NAME, type=ExchangeType.DIRECT, durable=True)

queue_new = RabbitQueue(QUEUE_NEW, routing_key=QUEUE_NEW, durable=True)

_settings = get_settings()

queue_retry_1 = RabbitQueue(
    QUEUE_RETRY_1,
    routing_key=QUEUE_RETRY_1,
    durable=True,
    arguments={
        "x-message-ttl": _settings.message_retry_base_delay_ms,
        "x-dead-letter-exchange": MAIN_EXCHANGE_NAME,
        "x-dead-letter-routing-key": QUEUE_NEW,
    },
)
queue_retry_2 = RabbitQueue(
    QUEUE_RETRY_2,
    routing_key=QUEUE_RETRY_2,
    durable=True,
    arguments={
        "x-message-ttl": _settings.message_retry_base_delay_ms * 2,
        "x-dead-letter-exchange": MAIN_EXCHANGE_NAME,
        "x-dead-letter-routing-key": QUEUE_NEW,
    },
)
queue_dlq = RabbitQueue(QUEUE_DLQ, routing_key=QUEUE_DLQ, durable=True)


async def declare_topology(broker: "RabbitBroker") -> None:
    """
    Idempotently declare and bind the full exchange/queue topology.

    Safe to call from every process that touches RabbitMQ (API's outbox
    relay, the consumer) regardless of startup order - AMQP declare/bind
    operations are no-ops when the target already exists with matching
    arguments, so there's no dependency on which process happens to run
    first against a fresh broker.
    """
    main = await broker.declare_exchange(main_exchange)
    dlx = await broker.declare_exchange(dlx_exchange)

    for queue in (queue_new, queue_retry_1, queue_retry_2):
        queue_obj = await broker.declare_queue(queue)
        await queue_obj.bind(main, routing_key=queue.routing_key)

    dlq_obj = await broker.declare_queue(queue_dlq)
    await dlq_obj.bind(dlx, routing_key=queue_dlq.routing_key)
