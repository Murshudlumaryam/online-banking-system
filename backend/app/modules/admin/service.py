import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.background_tasks.tasks import send_notification_task, write_audit_log_task
from app.core.exceptions import ConflictError, NotFoundError
from app.modules.accounts.models import Account, AccountStatus
from app.modules.accounts.repository import AccountRepository, generate_account_number
from app.modules.admin.schemas import (
    AdminCreateCustomerRequest,
    CreateAccountRequest,
    CreateCardRequest,
    CreateExchangeRateRequest,
    UpdateAccountStatusRequest,
    UpdateCustomerStatusRequest,
)
from app.modules.audit_logs.repository import AuditLogRepository
from app.modules.beneficiaries.models import Beneficiary, BeneficiaryStatus
from app.modules.beneficiaries.repository import BeneficiaryRepository
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
        self._cards = CardRepository(session)
        self._exchange_rates = ExchangeRateRepository(session)
        self._transactions = TransactionRepository(session)
        self._audit_logs = AuditLogRepository(session)
        self._beneficiaries = BeneficiaryRepository(session)

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------
    async def list_customers(self, *, page: int, page_size: int, status=None, search: str | None = None):
        return await self._customers.list_all(
            offset=(page - 1) * page_size, limit=page_size, status=status, search=search
        )

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
    async def list_accounts(self, *, page: int, page_size: int, status=None, search: str | None = None):
        return await self._accounts.list_all(
            offset=(page - 1) * page_size, limit=page_size, status=status, search=search
        )

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

    async def delete_card(self, admin_user: User, card_id: uuid.UUID) -> None:
        """
        Soft-deletes a card — never a physical DELETE. Matches the
        SoftDeleteMixin used elsewhere (users, customers, beneficiaries):
        a card's history has to remain reconstructable (which transactions
        it made, who used it and when) even after it's been "removed" from
        the customer's active list. Deleting is deliberately not
        restricted to already-blocked cards — an admin may need to remove
        a mistakenly-issued card immediately.
        """
        card = await self._cards.get_by_id(card_id)
        if card is None:
            raise NotFoundError("Card not found")

        await self._cards.soft_delete(card)
        await self._session.commit()

        write_audit_log_task.delay(
            str(admin_user.id), "ADMIN_CARD_DELETED", "card", str(card_id), None, None
        )

    # ------------------------------------------------------------------
    # Transactions (monitoring)
    # ------------------------------------------------------------------
    async def list_transactions(self, *, page: int, page_size: int, status=None, search: str | None = None):
        return await self._transactions.list_all(
            offset=(page - 1) * page_size, limit=page_size, status=status, search=search
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

    # ------------------------------------------------------------------
    # Cards (system-wide view)
    # ------------------------------------------------------------------
    async def list_cards(self, *, page: int, page_size: int, status=None):
        return await self._cards.list_all(offset=(page - 1) * page_size, limit=page_size, status=status)

    # ------------------------------------------------------------------
    # Beneficiaries (system-wide view)
    # ------------------------------------------------------------------
    async def list_beneficiaries(self, *, page: int, page_size: int):
        return await self._beneficiaries.list_all(offset=(page - 1) * page_size, limit=page_size)

    # ------------------------------------------------------------------
    # Customer onboarding (admin-initiated)
    # ------------------------------------------------------------------
    async def create_customer(
        self, admin_user: User, payload: AdminCreateCustomerRequest
    ) -> Customer:
        """Mirrors AuthService.register's TOCTOU-race handling (see that
        method's comments) — the same email/national_id UNIQUE constraints
        apply here, so the same IntegrityError -> clean ConflictError
        translation is needed rather than trusting the pre-checks alone."""
        from sqlalchemy.exc import IntegrityError

        from app.core.exceptions import ConflictError
        from app.core.security import hash_password
        from app.modules.users.repository import UserRepository

        users = UserRepository(self._session)
        if await users.email_exists(payload.email):
            raise ConflictError("A user with this email already exists")
        if await self._customers.national_id_exists(payload.national_id):
            raise ConflictError("A customer with this national ID already exists")

        try:
            user = users.create(email=payload.email, password_hash=hash_password(payload.temporary_password))
            await self._session.flush()

            customer = self._customers.create(
                user_id=user.id,
                first_name=payload.first_name,
                last_name=payload.last_name,
                date_of_birth=payload.date_of_birth,
                phone_number=payload.phone_number,
                address=payload.address,
                national_id=payload.national_id,
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("This email or national ID is already registered") from exc

        await self._session.refresh(customer)

        write_audit_log_task.delay(
            str(admin_user.id), "ADMIN_CUSTOMER_CREATED", "customer", str(customer.id), None,
            {"email": payload.email},
        )
        return customer

    # ------------------------------------------------------------------
    # Soft delete / restore (customers)
    # ------------------------------------------------------------------
    async def delete_customer(self, admin_user: User, customer_id: uuid.UUID) -> None:
        """
        Soft-deletes a customer — never a physical DELETE, per the same
        retention rule as cards (see CardService docstrings). The
        customer's accounts/transactions/ledger history all remain intact
        and queryable; the customer just stops appearing in normal admin
        listings (list_customers already filters deleted_at IS NULL) and
        can no longer log in as themselves in a customer-facing sense
        (their `Customer` row — the thing every customer-scoped dependency
        looks up — is gone from view). Does NOT touch their linked `User`
        row directly; restoring is symmetric and simple (just un-set
        deleted_at) precisely because nothing else was changed.
        """
        customer = await self._customers.get_by_id_including_deleted(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        if customer.deleted_at is not None:
            raise ConflictError("This customer is already deleted")

        await self._customers.soft_delete(customer)
        await self._session.commit()

        write_audit_log_task.delay(
            str(admin_user.id), "ADMIN_CUSTOMER_DELETED", "customer", str(customer_id), None, None
        )

    async def restore_customer(self, admin_user: User, customer_id: uuid.UUID) -> Customer:
        customer = await self._customers.get_by_id_including_deleted(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        if customer.deleted_at is None:
            raise ConflictError("This customer is not deleted")

        await self._customers.restore(customer)
        await self._session.commit()
        await self._session.refresh(customer)

        write_audit_log_task.delay(
            str(admin_user.id), "ADMIN_CUSTOMER_RESTORED", "customer", str(customer_id), None, None
        )
        return customer

    async def list_deleted_customers(self, *, page: int, page_size: int):
        return await self._customers.list_deleted(offset=(page - 1) * page_size, limit=page_size)

    # ------------------------------------------------------------------
    # Soft delete / restore (beneficiaries)
    # ------------------------------------------------------------------
    async def delete_beneficiary(self, admin_user: User, beneficiary_id: uuid.UUID) -> None:
        """Admin-initiated equivalent of a customer deleting their own
        beneficiary (see app.modules.beneficiaries.service — that path
        stays customer-only; this one exists for cases like a fraud
        investigation where an admin needs to remove a beneficiary the
        customer didn't or can't remove themselves)."""
        beneficiary = await self._beneficiaries.get_by_id_including_deleted(beneficiary_id)
        if beneficiary is None:
            raise NotFoundError("Beneficiary not found")
        if beneficiary.status == BeneficiaryStatus.DELETED:
            raise ConflictError("This beneficiary is already deleted")

        beneficiary.status = BeneficiaryStatus.DELETED
        beneficiary.deleted_at = datetime.now(timezone.utc)
        await self._beneficiaries.save(beneficiary)
        await self._session.commit()

        write_audit_log_task.delay(
            str(admin_user.id), "ADMIN_BENEFICIARY_DELETED", "beneficiary", str(beneficiary_id), None, None
        )

    async def restore_beneficiary(self, admin_user: User, beneficiary_id: uuid.UUID) -> Beneficiary:
        beneficiary = await self._beneficiaries.get_by_id_including_deleted(beneficiary_id)
        if beneficiary is None:
            raise NotFoundError("Beneficiary not found")
        if beneficiary.status != BeneficiaryStatus.DELETED:
            raise ConflictError("This beneficiary is not deleted")

        await self._beneficiaries.restore(beneficiary)
        await self._session.commit()
        await self._session.refresh(beneficiary)

        write_audit_log_task.delay(
            str(admin_user.id), "ADMIN_BENEFICIARY_RESTORED", "beneficiary", str(beneficiary_id), None, None
        )
        return beneficiary

    async def list_deleted_beneficiaries(self, *, page: int, page_size: int):
        return await self._beneficiaries.list_deleted(offset=(page - 1) * page_size, limit=page_size)

    # ------------------------------------------------------------------
    # Transaction reversal
    # ------------------------------------------------------------------
    async def reverse_transaction(
        self, admin_user: User, transaction_id: uuid.UUID, reason: str
    ) -> Transaction:
        from app.modules.transactions.service import TransactionService

        service = TransactionService(self._session)
        return await service.reverse_transaction(admin_user, transaction_id, reason)
