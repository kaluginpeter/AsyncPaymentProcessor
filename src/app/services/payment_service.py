import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.messaging.events import PAYMENT_CREATED, PaymentCreatedEvent
from app.models.outbox import OutboxEvent
from app.models.payment import Payment
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.payment_repository import PaymentRepository
from app.schemas.payment import PaymentCreateRequest
from app.services.exceptions import PaymentNotFoundError

logger = logging.getLogger(__name__)


class PaymentService:
    """
    Application service orchestrating payment creation and lookup.

    Creation writes the Payment row and its outbox event in a single
    transaction (the outbox pattern).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._payments = PaymentRepository(session)
        self._outbox = OutboxRepository(session)

    async def create_payment(self, request: PaymentCreateRequest, idempotency_key: str) -> Payment:
        existing = await self._payments.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            logger.info("idempotent replay for key=%s payment_id=%s", idempotency_key, existing.id)
            return existing
        payment_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        payment = Payment(
            id=payment_id,
            idempotency_key=idempotency_key,
            amount=request.amount,
            currency=request.currency,
            description=request.description,
            extra_metadata=request.metadata,
            webhook_url=str(request.webhook_url),
        )
        event = PaymentCreatedEvent(
            payment_id=payment_id,
            idempotency_key=idempotency_key,
            amount=request.amount,
            currency=request.currency.value,
            description=request.description,
            metadata=request.metadata,
            webhook_url=str(request.webhook_url),
            created_at=now,
        )
        outbox_event = OutboxEvent(
            aggregate_type="payment",
            aggregate_id=str(payment_id),
            event_type=PAYMENT_CREATED,
            payload=event.model_dump(mode="json"),
        )
        self._payments.add(payment)
        self._outbox.add(outbox_event)

        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            existing = await self._payments.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                logger.info("idempotency race resolved for key=%s payment_id=%s", idempotency_key, existing.id)
                return existing
            raise

        await self._session.refresh(payment)
        return payment

    async def get_payment(self, payment_id: uuid.UUID) -> Payment:
        payment = await self._payments.get_by_id(payment_id)
        if payment is None:
            raise PaymentNotFoundError(payment_id)
        return payment
