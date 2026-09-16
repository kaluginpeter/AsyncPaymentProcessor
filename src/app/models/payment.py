import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, Numeric, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JSONType = JSONB().with_variant(JSON(), "sqlite")


class Currency(str, enum.Enum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(Enum(Currency, name="currency"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column("metadata", JSONType, nullable=True)

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"),
        nullable=False,
        default=PaymentStatus.PENDING,
        index=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)

    webhook_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    webhook_delivered: Mapped[bool] = mapped_column(default=False, nullable=False)
    webhook_last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"Payment(id={self.id}, status={self.status}, amount={self.amount} {self.currency})"
