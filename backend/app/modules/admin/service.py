import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.background_tasks.tasks import send_notification_task, write_audit_log_task
from app.core.exceptions import AccountNotActiveError, CurrencyMismatchError, InsufficientBalanceError, NotFoundError
from app.modules.accounts.cash_operations import AccountCashOperationRepository, CashOperationType
from app.modules.accounts.models import Account, AccountStatus
from app.modules.accounts.repository import AccountRepository, generate_account_number
from app.modules.admin.schemas import (
    CreateAccountRequest,
    CreateCardRequest,
    CreateExchangeRateRequest,
    UpdateAccountStatusRequest,
    UpdateCustomerStatusRequest,
)
from app.modules.audit_logs.repository import AuditLogRepository
from app.modules.cards.models import Card
from app.modules.cards.repository import CardRepository, generate_synthetic_pan
from app.modules.customers.models import Customer
from app.modules.customers.repository import CustomerRepository
from app.modules.exchange_rates.models import ExchangeRate
from app.modules.exchange_rates.repository import ExchangeRateRepository
from app.modules.transactions.models import Transaction
from app.modules.transactions.repository import TransactionRepository
from app.modules.users.models import User


class AdminService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._customers = CustomerRepository(session)
        self._accounts = AccountRepository(session)
        self._cash_operations = AccountCashOperationRepository(session)
        self._cards = CardRepository(session)
        self._exchange_rates = ExchangeRateRepository(session)
        self._transactions = TransactionRepository(session)
        self._audit_logs = AuditLogRepository(session)

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------
    async def list_customers(self, *, page: int, page_size: int, status=None):
        return await self._customers.list_all(offset=(page - 1) * page_size, limit=page_size, status=status)

    async def get_customer(self, customer_id: uuid.UUID) -> Customer:
        customer = await self._customers.get_by_id(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        return customer

    async def update_customer_status(
        self, admin_user: User, customer_id: uuid.UUID, payload: UpdateCustomerStatusRequest
    ) -> Customer:
        customer = await self.get_customer(customer_id)
        previous_status = customer.status
        customer.status = payload.status
        await self._customers.save(customer)
        await self._session.commit()

        write_audit_log_task.delay(
            str(admin_user.id),
            "ADMIN_CUSTOMER_STATUS_CHANGED",
            "customer",
            str(customer.id),
            None,
            {"from": previous_status.value, "to": payload.status.value},
        )
        send_notification_task.delay(
            str(customer.user_id), "email", "account_status_changed", {"status": payload.status.value}
        )
        return customer

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------
    async def list_accounts(self, *, page: int, page_size: int, status=None):
        return await self._accounts.list_all(offset=(page - 1) * page_size, limit=page_size, status=status)

    async def create_account(self, admin_user: User, payload: CreateAccountRequest) -> Account:
        customer = await self.get_customer(payload.customer_id)

        account = self._accounts.create(
            customer_id=customer.id,
            account_number=generate_account_number(),
            account_type=payload.account_type,
            currency=payload.currency,
            status=AccountStatus.ACTIVE,
        )
        await self._session.commit()
        await self._session.refresh(account)

        write_audit_log_task.delay(
            str(admin_user.id), "ADMIN_ACCOUNT_CREATED", "account", str(account.id), None,
            {"customer_id": str(customer.id), "currency": payload.currency},
        )
        return account

    async def update_account_status(
        self, admin_user: User, account_id: uuid.UUID, payload: UpdateAccountStatusRequest
    ) -> Account:
        account = await self._accounts.get_by_id(account_id)
        if account is None:
            raise NotFoundError("Account not found")

        previous_status = account.status
        account.status = payload.status
        if payload.status == AccountStatus.CLOSED:
            from datetime import datetime, timezone

            account.closed_at = datetime.now(timezone.utc)
        await self._accounts.save(account)
        await self._session.commit()

        write_audit_log_task.delay(
            str(admin_user.id),
            "ADMIN_ACCOUNT_STATUS_CHANGED",
            "account",
            str(account.id),
            None,
            {"from": previous_status.value, "to": payload.status.value},
        )
        return account

    async def deposit_to_account(
        self, admin_user: User, account_id: uuid.UUID, *, amount, currency: str, note: str | None
    ) -> Account:
        return await self._apply_cash_operation(
            admin_user,
            account_id,
            amount=amount,
            currency=currency,
            note=note,
            operation_type=CashOperationType.DEPOSIT,
        )

    async def withdraw_from_account(
        self, admin_user: User, account_id: uuid.UUID, *, amount, currency: str, note: str | None
    ) -> Account:
        return await self._apply_cash_operation(
            admin_user,
            account_id,
            amount=amount,
            currency=currency,
            note=note,
            operation_type=CashOperationType.WITHDRAWAL,
        )

    async def _apply_cash_operation(
        self,
        admin_user: User,
        account_id: uuid.UUID,
        *,
        amount,
        currency: str,
        note: str | None,
        operation_type: CashOperationType,
    ) -> Account:
        account = await self._accounts.get_by_id_for_update(account_id)
        if account is None:
            raise NotFoundError("Account not found")
        if account.status != AccountStatus.ACTIVE:
            raise AccountNotActiveError(which="account")
        if account.currency != currency:
            raise CurrencyMismatchError(account.currency, currency)

        balance_before = account.balance
        if operation_type == CashOperationType.DEPOSIT:
            account.balance = account.balance + amount
            audit_action = "ADMIN_ACCOUNT_DEPOSITED"
        else:
            if account.balance < amount:
                raise InsufficientBalanceError()
            account.balance = account.balance - amount
            audit_action = "ADMIN_ACCOUNT_WITHDRAWN"

        account.version += 1
        self._cash_operations.create(
            account_id=account.id,
            operation_type=operation_type,
            amount=amount,
            currency=account.currency,
            balance_before=balance_before,
            balance_after=account.balance,
            performed_by_user_id=admin_user.id,
            note=note,
        )
        await self._accounts.save(account)
        await self._session.commit()
        await self._session.refresh(account)

        write_audit_log_task.delay(
            str(admin_user.id),
            audit_action,
            "account",
            str(account.id),
            None,
            {
                "amount": str(amount),
                "currency": account.currency,
                "balance_before": str(balance_before),
                "balance_after": str(account.balance),
            },
        )
        return account

    # ------------------------------------------------------------------
    # Cards
    # ------------------------------------------------------------------
    async def create_card(self, admin_user: User, payload: CreateCardRequest) -> Card:
        account = await self._accounts.get_by_id(payload.account_id)
        if account is None:
            raise NotFoundError("Account not found")

        expiry_date = date.today() + timedelta(days=365 * payload.validity_years)
        card = self._cards.create(
            account_id=account.id,
            raw_card_number=generate_synthetic_pan(),
            card_type=payload.card_type,
            expiry_date=expiry_date,
        )
        await self._session.commit()

        write_audit_log_task.delay(
            str(admin_user.id), "ADMIN_CARD_CREATED", "card", str(card.id), None,
            {"account_id": str(account.id)},
        )
        return card

    async def block_card(self, admin_user: User, card_id: uuid.UUID) -> Card:
        from datetime import datetime, timezone

        from app.modules.cards.models import CardStatus

        card = await self._cards.get_by_id(card_id)
        if card is None:
            raise NotFoundError("Card not found")

        card.status = CardStatus.BLOCKED
        card.blocked_at = datetime.now(timezone.utc)
        await self._cards.save(card)
        await self._session.commit()

        write_audit_log_task.delay(
            str(admin_user.id), "ADMIN_CARD_BLOCKED", "card", str(card.id), None, None
        )
        return card

    # ------------------------------------------------------------------
    # Transactions (monitoring)
    # ------------------------------------------------------------------
    async def list_transactions(self, *, page: int, page_size: int, status=None):
        return await self._transactions.list_all(
            offset=(page - 1) * page_size, limit=page_size, status=status
        )

    async def get_transaction(self, transaction_id: uuid.UUID) -> Transaction:
        transaction = await self._transactions.get_by_id(transaction_id)
        if transaction is None:
            raise NotFoundError("Transaction not found")
        return transaction

    # ------------------------------------------------------------------
    # Audit logs
    # ------------------------------------------------------------------
    async def list_audit_logs(self, *, page: int, page_size: int, **filters):
        return await self._audit_logs.list_all(
            offset=(page - 1) * page_size, limit=page_size, **filters
        )

    # ------------------------------------------------------------------
    # Exchange rates
    # ------------------------------------------------------------------
    async def list_all_exchange_rates(self) -> list[ExchangeRate]:
        return await self._exchange_rates.list_all()

    async def create_exchange_rate(
        self, admin_user: User, payload: CreateExchangeRateRequest
    ) -> ExchangeRate:
        rate = self._exchange_rates.create(
            source_currency=payload.source_currency,
            target_currency=payload.target_currency,
            rate=payload.rate,
        )
        await self._session.commit()
        await self._session.refresh(rate)

        write_audit_log_task.delay(
            str(admin_user.id),
            "ADMIN_EXCHANGE_RATE_CREATED",
            "exchange_rate",
            str(rate.id),
            None,
            {"pair": f"{payload.source_currency}->{payload.target_currency}", "rate": str(payload.rate)},
        )
        return rate
