import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.customers.dependencies import get_current_customer
from app.modules.customers.models import Customer
from app.modules.ledger_entries.schemas import LedgerEntryResponse
from app.modules.transactions.schemas import (
    ConfirmTransferRequest,
    InitiateTransferResponse,
    ResendOtpResponse,
    TransactionDetailResponse,
    TransactionResponse,
    TransferMoneyRequest,
)
from app.modules.transactions.service import TransactionService
from app.shared.schemas import PaginatedResponse

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


@router.post(
    "/transfer",
    response_model=InitiateTransferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate a money transfer (creates a PENDING transaction and sends an OTP)",
)
async def initiate_transfer(
    payload: TransferMoneyRequest,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> InitiateTransferResponse:
    service = TransactionService(session)
    transaction, expires_in_seconds = await service.initiate_transfer(customer, payload)
    return InitiateTransferResponse(
        transaction=TransactionResponse.model_validate(transaction),
        otp_expires_in_seconds=expires_in_seconds,
    )


@router.post(
    "/{transaction_id}/resend-otp",
    response_model=ResendOtpResponse,
    summary="Resend the OTP for a pending transfer (invalidates the previous code)",
)
async def resend_otp(
    transaction_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> ResendOtpResponse:
    service = TransactionService(session)
    expires_in_seconds = await service.resend_otp(customer, transaction_id)
    return ResendOtpResponse(otp_expires_in_seconds=expires_in_seconds)


@router.post(
    "/{transaction_id}/confirm",
    response_model=TransactionResponse,
    summary="Confirm a pending transfer with the OTP code",
)
async def confirm_transfer(
    transaction_id: uuid.UUID,
    payload: ConfirmTransferRequest,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    service = TransactionService(session)
    transaction = await service.confirm_transfer(customer, transaction_id, payload.otp_code)
    return TransactionResponse.model_validate(transaction)


@router.get(
    "",
    response_model=PaginatedResponse[TransactionResponse],
    summary="List the current customer's transactions (sent or received)",
)
async def list_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> PaginatedResponse[TransactionResponse]:
    service = TransactionService(session)
    transactions, total = await service.list_for_customer(customer, page=page, page_size=page_size)
    return PaginatedResponse[TransactionResponse](
        items=[TransactionResponse.model_validate(t) for t in transactions],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/search",
    response_model=TransactionResponse,
    summary="Find a transaction by its reference number",
)
async def search_transaction(
    reference: str = Query(..., min_length=1),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    service = TransactionService(session)
    transaction = await service.search_by_reference(customer, reference)
    return TransactionResponse.model_validate(transaction)


@router.get(
    "/{transaction_id}",
    response_model=TransactionDetailResponse,
    summary="Get transaction details including ledger entries",
)
async def get_transaction(
    transaction_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> TransactionDetailResponse:
    service = TransactionService(session)
    transaction = await service.get_owned_transaction(customer, transaction_id)
    ledger_entries = await service.get_ledger_entries(transaction.id)
    return TransactionDetailResponse(
        **TransactionResponse.model_validate(transaction).model_dump(),
        ledger_entries=[LedgerEntryResponse.model_validate(e) for e in ledger_entries],
    )


@router.get(
    "/{transaction_id}/debug-otp",
    include_in_schema=False,
    summary="[test environment only] Reads the OTP an e2e test just triggered",
)
async def debug_get_otp(
    transaction_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
) -> dict:
    from fastapi import HTTPException

    from app.core import test_otp_store

    if not test_otp_store.is_enabled():
        # Deliberately identical to a normal 404 — this route must be
        # indistinguishable from "doesn't exist" in every non-test environment.
        raise HTTPException(status_code=404, detail="Not Found")

    code = test_otp_store.pop(transaction_id)
    if code is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return {"otp_code": code}
