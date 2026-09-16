import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

PAYMENT_CREATED = "payment.created"


class PaymentCreatedEvent(BaseModel):
    """Payload published to the `payments.new` queue via the transactional outbox."""

    payment_id: uuid.UUID
    idempotency_key: str
    amount: Decimal
    currency: str
    description: str | None = None
    metadata: dict[str, Any] | None = None
    webhook_url: str
    created_at: datetime
