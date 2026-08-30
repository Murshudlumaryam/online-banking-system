import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.accounts.models import AccountStatus
from app.modules.accounts.schemas import AccountResponse
from app.modules.admin.schemas import (
    AdminCreateCustomerRequest,
    CreateAccountRequest,
    CreateCardRequest,
    CreateExchangeRateRequest,
    ReverseTransactionRequest,
    UpdateAccountStatusRequest,
    UpdateCustomerStatusRequest,
)
from app.modules.admin.service import AdminService
from app.modules.audit_logs.schemas import AuditLogResponse
from app.modules.auth.dependencies import require_admin
from app.modules.beneficiaries.schemas import BeneficiaryResponse
from app.modules.cards.models import CardStatus
from app.modules.cards.schemas import CardResponse
from app.modules.customers.models import CustomerStatus
from app.modules.customers.schemas import CustomerProfileResponse
from app.modules.exchange_rates.schemas import ExchangeRateResponse
from app.modules.ledger_entries.repository import LedgerEntryRepository
from app.modules.ledger_entries.schemas import LedgerEntryResponse
from app.modules.transactions.models import TransactionStatus
from app.modules.transactions.schemas import (
    DepositRequest,
    TransactionDetailResponse,
    TransactionResponse,
    WithdrawalRequest,
)
from app.modules.transactions.service import TransactionService
from app.modules.users.models import User
from app.shared.schemas import PaginatedResponse

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ----------------------------------------------------------------------
# Customers
# ----------------------------------------------------------------------
@router.get(
    "/customers",
    response_model=PaginatedResponse[CustomerProfileResponse],
    summary="List all customers (admin)",
)
async def list_customers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: CustomerStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(
        default=None, description="Matches name, email, phone, national ID, or customer number"
    ),
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> PaginatedResponse[CustomerProfileResponse]:
    service = AdminService(session)
    customers, total = await service.list_customers(
        page=page, page_size=page_size, status=status_filter, search=search
    )
    return PaginatedResponse[CustomerProfileResponse](
        items=[CustomerProfileResponse.model_validate(c) for c in customers],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/customers/deleted",
    response_model=PaginatedResponse[CustomerProfileResponse],
    summary="List soft-deleted customers (registered before /customers/{customer_id} so 'deleted' isn't parsed as an id)",
)
async def list_deleted_customers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> PaginatedResponse[CustomerProfileResponse]:
    service = AdminService(session)
    customers, total = await service.list_deleted_customers(page=page, page_size=page_size)
    return PaginatedResponse[CustomerProfileResponse](
        items=[CustomerProfileResponse.model_validate(c) for c in customers],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/customers/{customer_id}",
    response_model=CustomerProfileResponse,
    summary="Get a customer's profile (admin)",
)
async def get_customer(
    customer_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> CustomerProfileResponse:
    service = AdminService(session)
    customer = await service.get_customer(customer_id)
    return CustomerProfileResponse.model_validate(customer)


@router.delete(
    "/customers/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a customer (soft delete — history is preserved, restorable)",
)
async def delete_customer(
    customer_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> None:
    service = AdminService(session)
    await service.delete_customer(admin_user, customer_id)


@router.post(
    "/customers/{customer_id}/restore",
    response_model=CustomerProfileResponse,
    summary="Restore a previously soft-deleted customer",
)
async def restore_customer(
    customer_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> CustomerProfileResponse:
    service = AdminService(session)
    customer = await service.restore_customer(admin_user, customer_id)
    return CustomerProfileResponse.model_validate(customer)


@router.patch(
    "/customers/{customer_id}/status",
    response_model=CustomerProfileResponse,
    summary="Activate or block a customer",
)
async def update_customer_status(
    customer_id: uuid.UUID,
    payload: UpdateCustomerStatusRequest,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> CustomerProfileResponse:
    service = AdminService(session)
    customer = await service.update_customer_status(admin_user, customer_id, payload)
    return CustomerProfileResponse.model_validate(customer)


@router.post(
    "/customers",
    response_model=CustomerProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open an account for a customer who can't self-register (e.g. a walk-in branch customer)",
)
async def create_customer(
    payload: AdminCreateCustomerRequest,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> CustomerProfileResponse:
    service = AdminService(session)
    customer = await service.create_customer(admin_user, payload)
    return CustomerProfileResponse.model_validate(customer)


# ----------------------------------------------------------------------
# Accounts
# ----------------------------------------------------------------------
@router.get(
    "/accounts", response_model=PaginatedResponse[AccountResponse], summary="List all accounts (admin)"
)
async def list_accounts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: AccountStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, description="Matches account number"),
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> PaginatedResponse[AccountResponse]:
    service = AdminService(session)
    accounts, total = await service.list_accounts(
        page=page, page_size=page_size, status=status_filter, search=search
    )
    return PaginatedResponse[AccountResponse](
        items=[AccountResponse.model_validate(a) for a in accounts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/accounts",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account for a customer",
)
async def create_account(
    payload: CreateAccountRequest,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AccountResponse:
    service = AdminService(session)
    account = await service.create_account(admin_user, payload)
    return AccountResponse.model_validate(account)


@router.post(
    "/accounts/{account_id}/deposit",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Deposit money into a customer's account",
)
async def deposit_to_account(
    account_id: uuid.UUID,
    payload: DepositRequest,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    """
    Credits money into `account_id` from outside this closed-loop system —
    e.g. cash handed to a teller, or an incoming external wire this system
    has no real integration to receive automatically. Admin-only: there is
    no self-service "add money" for a customer here, since (unlike a
    transfer between two of this system's own accounts) there's no
    counterparty account to debit and therefore nothing a customer's own
    credentials alone could legitimately authorize.
    """
    service = TransactionService(session)
    transaction = await service.deposit(
        account_id=account_id,
        amount=payload.amount,
        currency=payload.currency,
        note=payload.note,
        performed_by_user_id=admin_user.id,
    )
    return TransactionResponse.model_validate(transaction)


@router.post(
    "/accounts/{account_id}/withdraw",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Withdraw money from a customer's account",
)
async def withdraw_from_account(
    account_id: uuid.UUID,
    payload: WithdrawalRequest,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    """The withdrawal counterpart of `deposit_to_account` — debits
    `account_id` for money leaving the system (e.g. cash paid out at a
    branch). See that endpoint's docstring for why this is admin-only."""
    service = TransactionService(session)
    transaction = await service.withdraw(
        account_id=account_id,
        amount=payload.amount,
        currency=payload.currency,
        note=payload.note,
        performed_by_user_id=admin_user.id,
    )
    return TransactionResponse.model_validate(transaction)


@router.patch(
    "/accounts/{account_id}/status",
    response_model=AccountResponse,
    summary="Change an account's status (ACTIVE/BLOCKED/CLOSED/PENDING)",
)
async def update_account_status(
    account_id: uuid.UUID,
    payload: UpdateAccountStatusRequest,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AccountResponse:
    service = AdminService(session)
    account = await service.update_account_status(admin_user, account_id, payload)
    return AccountResponse.model_validate(account)


# ----------------------------------------------------------------------
# Cards
# ----------------------------------------------------------------------
@router.get(
    "/cards",
    response_model=PaginatedResponse[CardResponse],
    summary="List every card issued across all customers",
)
async def list_cards(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: CardStatus | None = Query(default=None, alias="status"),
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> PaginatedResponse[CardResponse]:
    service = AdminService(session)
    cards, total = await service.list_cards(page=page, page_size=page_size, status=status_filter)
    return PaginatedResponse[CardResponse](
        items=[CardResponse.model_validate(c) for c in cards],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/cards",
    response_model=CardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a new card for an account",
)
async def create_card(
    payload: CreateCardRequest,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> CardResponse:
    service = AdminService(session)
    card = await service.create_card(admin_user, payload)
    return CardResponse.model_validate(card)


@router.patch("/cards/{card_id}/block", response_model=CardResponse, summary="Block a card")
async def block_card(
    card_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> CardResponse:
    service = AdminService(session)
    card = await service.block_card(admin_user, card_id)
    return CardResponse.model_validate(card)


@router.delete(
    "/cards/{card_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a card (soft delete — its history is preserved, not shown to the customer)",
)
async def delete_card(
    card_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> None:
    service = AdminService(session)
    await service.delete_card(admin_user, card_id)


# ----------------------------------------------------------------------
# Beneficiaries
# ----------------------------------------------------------------------
@router.get(
    "/beneficiaries",
    response_model=PaginatedResponse[BeneficiaryResponse],
    summary="List every customer's saved beneficiaries",
)
async def list_beneficiaries(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> PaginatedResponse[BeneficiaryResponse]:
    service = AdminService(session)
    beneficiaries, total = await service.list_beneficiaries(page=page, page_size=page_size)
    return PaginatedResponse[BeneficiaryResponse](
        items=[BeneficiaryResponse.model_validate(b) for b in beneficiaries],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/beneficiaries/deleted",
    response_model=PaginatedResponse[BeneficiaryResponse],
    summary="List soft-deleted beneficiaries",
)
async def list_deleted_beneficiaries(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> PaginatedResponse[BeneficiaryResponse]:
    service = AdminService(session)
    beneficiaries, total = await service.list_deleted_beneficiaries(page=page, page_size=page_size)
    return PaginatedResponse[BeneficiaryResponse](
        items=[BeneficiaryResponse.model_validate(b) for b in beneficiaries],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete(
    "/beneficiaries/{beneficiary_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a beneficiary (soft delete — restorable)",
)
async def delete_beneficiary(
    beneficiary_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> None:
    service = AdminService(session)
    await service.delete_beneficiary(admin_user, beneficiary_id)


@router.post(
    "/beneficiaries/{beneficiary_id}/restore",
    response_model=BeneficiaryResponse,
    summary="Restore a previously soft-deleted beneficiary",
)
async def restore_beneficiary(
    beneficiary_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> BeneficiaryResponse:
    service = AdminService(session)
    beneficiary = await service.restore_beneficiary(admin_user, beneficiary_id)
    return BeneficiaryResponse.model_validate(beneficiary)


# ----------------------------------------------------------------------
# Transactions (monitoring)
# ----------------------------------------------------------------------
@router.get(
    "/transactions",
    response_model=PaginatedResponse[TransactionResponse],
    summary="List/monitor all transactions across all customers",
)
async def list_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: TransactionStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, description="Matches the reference number (e.g. TXN-...)"),
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> PaginatedResponse[TransactionResponse]:
    service = AdminService(session)
    transactions, total = await service.list_transactions(
        page=page, page_size=page_size, status=status_filter, search=search
    )
    return PaginatedResponse[TransactionResponse](
        items=[TransactionResponse.model_validate(t) for t in transactions],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/transactions/{transaction_id}",
    response_model=TransactionDetailResponse,
    summary="Get any transaction's full detail including ledger entries",
)
async def get_transaction(
    transaction_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> TransactionDetailResponse:
    service = AdminService(session)
    transaction = await service.get_transaction(transaction_id)
    ledger_entries = await LedgerEntryRepository(session).list_for_transaction(transaction.id)
    return TransactionDetailResponse(
        **TransactionResponse.model_validate(transaction).model_dump(),
        ledger_entries=[LedgerEntryResponse.model_validate(e) for e in ledger_entries],
    )


@router.post(
    "/transactions/{transaction_id}/reverse",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Reverse a completed transaction (creates a new, opposite-direction transaction)",
)
async def reverse_transaction(
    transaction_id: uuid.UUID,
    payload: ReverseTransactionRequest,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    service = AdminService(session)
    reversal = await service.reverse_transaction(admin_user, transaction_id, payload.reason)
    return TransactionResponse.model_validate(reversal)


# ----------------------------------------------------------------------
# Audit logs
# ----------------------------------------------------------------------
@router.get(
    "/audit-logs", response_model=PaginatedResponse[AuditLogResponse], summary="Search the audit trail"
)
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    request_id: str | None = Query(default=None),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> PaginatedResponse[AuditLogResponse]:
    service = AdminService(session)
    logs, total = await service.list_audit_logs(
        page=page,
        page_size=page_size,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        status=status_filter,
        request_id=request_id,
        created_after=created_after,
        created_before=created_before,
    )
    return PaginatedResponse[AuditLogResponse](
        items=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


# ----------------------------------------------------------------------
# Exchange rates
# ----------------------------------------------------------------------
@router.get(
    "/exchange-rates",
    response_model=list[ExchangeRateResponse],
    summary="List all exchange rates including inactive/expired ones",
)
async def list_exchange_rates(
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> list[ExchangeRateResponse]:
    service = AdminService(session)
    rates = await service.list_all_exchange_rates()
    return [ExchangeRateResponse.model_validate(r) for r in rates]


@router.post(
    "/exchange-rates",
    response_model=ExchangeRateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new exchange rate",
)
async def create_exchange_rate(
    payload: CreateExchangeRateRequest,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> ExchangeRateResponse:
    service = AdminService(session)
    rate = await service.create_exchange_rate(admin_user, payload)
    return ExchangeRateResponse.model_validate(rate)


@router.post(
    "/accounts/{account_id}/debug-set-balance",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
    summary="[test environment only] Directly sets an account's balance for test fixture setup",
)
async def debug_set_account_balance(
    account_id: uuid.UUID,
    amount: str,
    session: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> None:
    """
    There is no real "deposit" feature in this closed-loop banking system —
    money only ever moves between two of its own accounts via a transfer.
    That's a deliberate product-scope decision, not an oversight, but it
    means automated tests (including these e2e specs) need *some* way to
    seed a starting balance without a real originating transfer. Gated
    identically to every other debug-* route in this codebase.
    """
    from decimal import Decimal

    from fastapi import HTTPException

    from app.core.test_mode import is_test_environment
    from app.modules.accounts.repository import AccountRepository

    if not is_test_environment():
        raise HTTPException(status_code=404, detail="Not Found")

    accounts = AccountRepository(session)
    account = await accounts.get_by_id(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Not Found")

    account.balance = Decimal(amount)
    await accounts.save(account)
    await session.commit()
