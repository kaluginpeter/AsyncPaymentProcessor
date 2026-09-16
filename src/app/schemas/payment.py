import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models.payment import Currency, PaymentStatus


class PaymentCreateRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, description="Payment amount, must be positive")
    currency: Currency
    description: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] | None = Field(default=None)
    webhook_url: HttpUrl

    @field_validator("amount")
    @classmethod
    def quantize_amount(cls, value: Decimal) -> Decimal:
        # Reject invalid precision
        if value.as_tuple().exponent < -2:
            raise ValueError("amount must not have more than 2 decimal places")
        return value


class PaymentCreateResponse(BaseModel):
    payment_id: uuid.UUID = Field(validation_alias="id")
    status: PaymentStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PaymentDetailResponse(BaseModel):
    payment_id: uuid.UUID = Field(validation_alias="id")
    idempotency_key: str
    amount: Decimal
    currency: Currency
    description: str | None
    metadata: dict[str, Any] | None = Field(validation_alias="extra_metadata")
    status: PaymentStatus
    failure_reason: str | None
    webhook_url: str
    webhook_delivered: bool
    created_at: datetime
    processed_at: datetime | None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
