import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, verify_api_key
from app.schemas.payment import PaymentCreateRequest, PaymentCreateResponse, PaymentDetailResponse
from app.services.exceptions import PaymentNotFoundError
from app.services.payment_service import PaymentService

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
    dependencies=[Depends(verify_api_key)],
)


@router.post(
    "",
    response_model=PaymentCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a payment and enqueue it for asynchronous processing",
)
async def create_payment(
    body: PaymentCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=255),
    session: AsyncSession = Depends(get_db),
) -> PaymentCreateResponse:
    service = PaymentService(session)
    payment = await service.create_payment(body, idempotency_key)
    return PaymentCreateResponse.model_validate(payment)


@router.get(
    "/{payment_id}",
    response_model=PaymentDetailResponse,
    summary="Fetch the current state of a payment",
)
async def get_payment(
    payment_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> PaymentDetailResponse:
    service = PaymentService(session)
    try:
        payment = await service.get_payment(payment_id)
    except PaymentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PaymentDetailResponse.model_validate(payment)
