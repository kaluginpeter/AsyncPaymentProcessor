import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent
from app.models.payment import Currency, Payment, PaymentStatus
from app.schemas.payment import PaymentCreateRequest
from app.services.exceptions import PaymentNotFoundError
from app.services.payment_service import PaymentService


def _request(**overrides) -> PaymentCreateRequest:
    defaults = dict(
        amount="10.00",
        currency=Currency.RUB,
        description="test",
        metadata={"k": "v"},
        webhook_url="http://example.com/webhook",
    )
    defaults.update(overrides)
    return PaymentCreateRequest(**defaults)


async def test_create_payment_writes_payment_and_outbox_event_atomically(session: AsyncSession) -> None:
    service = PaymentService(session)

    payment = await service.create_payment(_request(), idempotency_key="key-1")

    assert payment.status == PaymentStatus.PENDING
    assert payment.amount == payment.amount  # sanity

    outbox_rows = (await session.execute(select(OutboxEvent))).scalars().all()
    assert len(outbox_rows) == 1
    assert outbox_rows[0].aggregate_id == str(payment.id)
    assert outbox_rows[0].event_type == "payment.created"


async def test_create_payment_is_idempotent_for_same_key(session: AsyncSession) -> None:
    service = PaymentService(session)

    first = await service.create_payment(_request(), idempotency_key="dup-key")
    second = await service.create_payment(_request(amount="99.00"), idempotency_key="dup-key")

    assert first.id == second.id
    assert second.amount == Decimal("10.00")  # the second call's body was ignored; original amount kept

    payments = (await session.execute(select(Payment))).scalars().all()
    assert len(payments) == 1

    outbox_rows = (await session.execute(select(OutboxEvent))).scalars().all()
    assert len(outbox_rows) == 1


async def test_create_payment_recovers_from_unique_constraint_race(session: AsyncSession, monkeypatch) -> None:
    """
    Simulates two requests racing on the same idempotency key: both read "no
    existing payment" before either has committed, so only the DB's unique
    index actually prevents the duplicate. The loser's insert must fail
    over to returning the winner's row instead of surfacing a 500.
    """
    service = PaymentService(session)
    winner = await service.create_payment(_request(), idempotency_key="race")

    real_precheck = service._payments.get_by_idempotency_key
    calls = {"n": 0}

    async def precheck_that_misses_once(key: str):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # pretend the row isn't visible yet, as in a real race
        return await real_precheck(key)

    monkeypatch.setattr(service._payments, "get_by_idempotency_key", precheck_that_misses_once)

    loser_result = await service.create_payment(_request(amount="55.00"), idempotency_key="race")

    assert loser_result.id == winner.id

    payments = (await session.execute(select(Payment))).scalars().all()
    assert len(payments) == 1


async def test_get_payment_returns_created_payment(session: AsyncSession) -> None:
    service = PaymentService(session)
    created = await service.create_payment(_request(), idempotency_key="lookup-key")

    fetched = await service.get_payment(created.id)

    assert fetched.id == created.id


async def test_get_payment_raises_for_unknown_id(session: AsyncSession) -> None:
    service = PaymentService(session)
    with pytest.raises(PaymentNotFoundError):
        await service.get_payment(uuid.uuid4())
