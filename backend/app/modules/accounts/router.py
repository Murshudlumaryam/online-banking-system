from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.accounts.dependencies import get_owned_account
from app.modules.accounts.cash_operations import AccountCashOperationRepository
from app.modules.accounts.models import Account
from app.modules.accounts.repository import AccountRepository
from app.modules.accounts.schemas import AccountBalanceResponse, AccountResponse
from app.modules.accounts.statement import generate_account_statement_pdf
from app.modules.customers.dependencies import get_current_customer
from app.modules.customers.models import Customer
from app.modules.ledger_entries.repository import LedgerEntryRepository

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse], summary="List the current customer's accounts")
async def list_accounts(
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> list[AccountResponse]:
    accounts = await AccountRepository(session).list_for_customer(customer.id)
    return [AccountResponse.model_validate(a) for a in accounts]


@router.get("/{account_id}", response_model=AccountResponse, summary="Get account details")
async def get_account(account: Account = Depends(get_owned_account)) -> AccountResponse:
    return AccountResponse.model_validate(account)


@router.get(
    "/{account_id}/balance",
    response_model=AccountBalanceResponse,
    summary="Get the current balance of an account",
)
async def get_account_balance(account: Account = Depends(get_owned_account)) -> AccountBalanceResponse:
    return AccountBalanceResponse(
        account_id=account.id, currency=account.currency, balance=account.balance
    )


@router.get(
    "/{account_id}/statement",
    summary="Download a PDF account statement for a date range (defaults to the last 30 days)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def get_account_statement(
    account: Account = Depends(get_owned_account),
    customer: Customer = Depends(get_current_customer),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> Response:
    resolved_end_date = end_date or datetime.now(timezone.utc).date()
    resolved_start_date = start_date or (resolved_end_date - timedelta(days=30))

    start_datetime = datetime.combine(resolved_start_date, time.min, tzinfo=timezone.utc)
    end_datetime = datetime.combine(resolved_end_date, time.max, tzinfo=timezone.utc)

    entries = await LedgerEntryRepository(session).list_for_account(
        account.id, start=start_datetime, end=end_datetime
    )
    cash_operations = await AccountCashOperationRepository(session).list_for_account(
        account.id, start=start_datetime, end=end_datetime
    )
    pdf_bytes = generate_account_statement_pdf(
        account=account,
        customer=customer,
        entries=entries,
        cash_operations=cash_operations,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
    )
    filename = f"statement-{account.account_number}-{resolved_start_date}-to-{resolved_end_date}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
