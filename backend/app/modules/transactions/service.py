from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.background_tasks.tasks import send_notification_task, write_audit_log_task
from app.core.config import get_settings
from app.core.exceptions import (
    AccountNotActiveError,
    CurrencyMismatchError,
    DomainError,
    ExchangeRateNotFoundError,
    InsufficientBalanceError,
    InvalidOtpError,
    NotFoundError,
    OtpExpiredError,
    SameAccountTransferError,
    TooManyOtpAttemptsError,
    TransactionAlreadyProcessedError,
)
from app.core.security import generate_otp_code, hash_otp_code, verify_otp_code
from app.modules.accounts.models import AccountStatus
from app.modules.accounts.repository import AccountRepository
from app.modules.customers.models import Customer
from app.modules.exchange_rates.repository import ExchangeRateRepository
from app.modules.ledger_entries.models import LedgerEntryType
from app.modules.ledger_entries.repository import LedgerEntryRepository
from app.modules.transactions.models import Transaction, TransactionStatus
from app.modules.transactions.repository import (
    TransactionRepository,
    TransferConfirmationRepository,
)
from app.modules.transactions.schemas import TransferMoneyRequest

settings = get_settings()


class TransactionService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._accounts = AccountRepository(session)
        self._transactions = TransactionRepository(session)
        self._confirmations = TransferConfirmationRepository(session)
        self._ledger_entries = LedgerEntryRepository(session)
        self._exchange_rates = ExchangeRateRepository(session)

    # ------------------------------------------------------------------
    # Shared validation: used by both the interactive (OTP) transfer flow
    # and scheduled/recurring payments (Phase 7) — same business rules
    # either way, only what happens *after* the transaction row exists
    # differs (wait for OTP vs. execute immediately since a scheduled
    # payment was already authorized when the schedule was created).
    # ------------------------------------------------------------------
    async def _validate_and_create_pending_transaction(
        self,
        customer: Customer,
        *,
        sender_account_id,
        receiver_account_number: str,
        amount: Decimal,
        currency: str,
    ) -> Transaction:
        sender = await self._accounts.get_by_id(sender_account_id)
        if sender is None or sender.customer_id != customer.id:
            raise NotFoundError("Sender account not found")

        if sender.status != AccountStatus.ACTIVE:
            raise AccountNotActiveError(which="sender account")

        if currency != sender.currency:
            raise CurrencyMismatchError(sender.currency, currency)

        receiver = await self._accounts.get_by_account_number(receiver_account_number)
        if receiver is None:
            raise NotFoundError("Receiver account not found")

        if receiver.id == sender.id:
            raise SameAccountTransferError()

        if receiver.status != AccountStatus.ACTIVE:
            raise AccountNotActiveError(which="receiver account")

        if sender.balance < amount:
            raise InsufficientBalanceError()

        exchange_rate_id = None
        converted_amount = amount
        if sender.currency != receiver.currency:
            rate = await self._exchange_rates.get_active_rate(sender.currency, receiver.currency)
            if rate is None:
                raise ExchangeRateNotFoundError(sender.currency, receiver.currency)
            exchange_rate_id = rate.id
            converted_amount = (amount * rate.rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        transaction = self._transactions.create(
            sender_account_id=sender.id,
            receiver_account_id=receiver.id,
            amount=amount,
            currency=sender.currency,
            exchange_rate_id=exchange_rate_id,
            converted_amount=converted_amount,
        )
        await self._session.flush()  # assign transaction.id
        return transaction

    # ------------------------------------------------------------------
    # Step 1: initiate — validate everything, create a PENDING transaction
    # and an OTP challenge. No money moves yet.
    # ------------------------------------------------------------------
    async def initiate_transfer(
        self, customer: Customer, payload: TransferMoneyRequest
    ) -> tuple[Transaction, int]:
        transaction = await self._validate_and_create_pending_transaction(
            customer,
            sender_account_id=payload.sender_account_id,
            receiver_account_number=payload.receiver_account_number,
            amount=payload.amount,
            currency=payload.currency,
        )

        otp_code = generate_otp_code()
        expires_in_seconds = settings.otp_expire_minutes * 60
        from datetime import datetime, timedelta, timezone

        from app.core import test_otp_store

        test_otp_store.capture(transaction.id, otp_code)

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes)
        self._confirmations.create(
            transaction_id=transaction.id,
            otp_code_hash=hash_otp_code(otp_code),
            expires_at=expires_at,
        )
        await self._session.commit()

        # The OTP is delivered only through the notification channel — it is
        # never included in the HTTP response and never written to logs.
        send_notification_task.delay(
            str(customer.user_id),
            "sms",
            "transfer_otp",
            {"otp_code": otp_code, "reference_number": transaction.reference_number},
        )
        write_audit_log_task.delay(
            str(customer.user_id),
            "TRANSFER_INITIATED",
            "transaction",
            str(transaction.id),
            None,
            {"reference_number": transaction.reference_number},
        )
        return transaction, expires_in_seconds

    # ------------------------------------------------------------------
    # Step 2: confirm — verify OTP, then atomically lock both accounts,
    # move the money, and write balanced ledger entries. Any failure at
    # this stage rolls back completely and the transaction is marked
    # FAILED (never left PENDING, never partially applied).
    # ------------------------------------------------------------------
    async def confirm_transfer(
        self, customer: Customer, transaction_id, otp_code: str
    ) -> Transaction:
        transaction = await self._get_owned_pending_transaction(customer, transaction_id)

        confirmation = await self._confirmations.get_by_transaction_id(transaction.id)
        if confirmation is None:
            raise NotFoundError("No OTP challenge found for this transaction")

        if self._confirmations.is_expired(confirmation):
            await self._transactions.mark_failed(transaction, "OTP expired")
            await self._session.commit()
            from app.core.metrics import transfers_total

            transfers_total.labels(outcome="failed").inc()
            raise OtpExpiredError()

        if self._confirmations.attempts_exhausted(confirmation):
            await self._transactions.mark_failed(transaction, "Too many invalid OTP attempts")
            await self._session.commit()
            from app.core.metrics import transfers_total

            transfers_total.labels(outcome="otp_invalid").inc()
            raise TooManyOtpAttemptsError()

        if not verify_otp_code(otp_code, confirmation.otp_code_hash):
            await self._confirmations.register_failed_attempt(confirmation)
            attempts_remaining = confirmation.max_attempts - confirmation.attempts
            from app.core.metrics import transfers_total

            if attempts_remaining <= 0:
                await self._transactions.mark_failed(transaction, "Too many invalid OTP attempts")
                await self._session.commit()
                transfers_total.labels(outcome="otp_invalid").inc()
                raise TooManyOtpAttemptsError()
            await self._session.commit()
            transfers_total.labels(outcome="otp_invalid").inc()
            raise InvalidOtpError(attempts_remaining)

        transaction = await self._execute_locked_transfer(transaction)
        transaction.otp_verified = True
        await self._confirmations.mark_verified(confirmation)
        await self._session.commit()

        write_audit_log_task.delay(
            str(customer.user_id),
            "TRANSFER_COMPLETED",
            "transaction",
            str(transaction.id),
            None,
            {"reference_number": transaction.reference_number},
        )
        send_notification_task.delay(
            str(customer.user_id),
            "sms",
            "transfer_completed",
            {"reference_number": transaction.reference_number},
        )
        return transaction

    async def _execute_locked_transfer(self, transaction: Transaction) -> Transaction:
        """
        Atomically locks both accounts (ordered by id to prevent deadlocks),
        moves the money, and writes balanced ledger entries. On any
        domain-rule violation discovered under lock (account state changed
        since the transaction row was created), rolls back and marks the
        transaction FAILED — unless a concurrent request already resolved
        it, in which case that outcome is preserved rather than overwritten
        (see the race-condition fix in Phase 3's README write-up) and
        TransactionAlreadyProcessedError is raised instead.
        """
        try:
            locked_accounts = await self._accounts.get_two_for_update(
                transaction.sender_account_id, transaction.receiver_account_id
            )
            sender = locked_accounts[transaction.sender_account_id]
            receiver = locked_accounts[transaction.receiver_account_id]

            if sender.status != AccountStatus.ACTIVE:
                raise AccountNotActiveError(which="sender account")
            if receiver.status != AccountStatus.ACTIVE:
                raise AccountNotActiveError(which="receiver account")
            if sender.balance < transaction.amount:
                raise InsufficientBalanceError()

            credit_amount = (
                transaction.converted_amount
                if transaction.converted_amount is not None
                else transaction.amount
            )

            sender_balance_before = sender.balance
            sender.balance = sender.balance - transaction.amount
            sender.version += 1

            receiver_balance_before = receiver.balance
            receiver.balance = receiver.balance + credit_amount
            receiver.version += 1

            self._ledger_entries.create(
                transaction_id=transaction.id,
                account_id=sender.id,
                entry_type=LedgerEntryType.DEBIT,
                amount=transaction.amount,
                currency=sender.currency,
                balance_before=sender_balance_before,
                balance_after=sender.balance,
            )
            self._ledger_entries.create(
                transaction_id=transaction.id,
                account_id=receiver.id,
                entry_type=LedgerEntryType.CREDIT,
                amount=credit_amount,
                currency=receiver.currency,
                balance_before=receiver_balance_before,
                balance_after=receiver.balance,
            )

            await self._transactions.mark_success(transaction)
            await self._session.commit()
            from app.core.metrics import transfers_total

            transfers_total.labels(outcome="success").inc()
            return transaction
        except DomainError as exc:
            # Capture the id as a plain value BEFORE rollback — after
            # `rollback()`, every ORM object tied to this session (including
            # `transaction`) is expired by default, and accessing even a
            # simple attribute like `transaction.id` afterward triggers an
            # implicit lazy-reload. In async SQLAlchemy that reload must be
            # awaited explicitly; a bare attribute access can't do that and
            # raises `MissingGreenlet` — which would abort this except block
            # entirely, skipping `mark_failed` and leaving the loser's
            # transaction stuck at PENDING instead of FAILED. Found via a
            # real concurrent-load test (two separate transfers racing for
            # the same sender account) — see
            # tests/modules/transactions/test_audit_concurrency.py.
            transaction_id = transaction.id
            await self._session.rollback()
            reloaded_transaction = await self._transactions.get_by_id(transaction_id)
            assert reloaded_transaction is not None, "transaction disappeared mid-execution"
            if reloaded_transaction.status == TransactionStatus.PENDING:
                # Still ours to fail — no concurrent request resolved it first.
                await self._transactions.mark_failed(reloaded_transaction, str(exc))
                await self._session.commit()
                from app.core.metrics import transfers_total

                transfers_total.labels(outcome="failed").inc()
                raise
            # A concurrent request already resolved this transaction — never
            # overwrite an already-SUCCESS/FAILED row. Surface a
            # non-destructive error instead.
            raise TransactionAlreadyProcessedError() from exc

    # ------------------------------------------------------------------
    # Scheduled / recurring payments (Phase 7): the customer already gave
    # standing authorization when creating the schedule, so execution skips
    # the interactive OTP step — it goes straight through the same
    # validation + locked-execution core as an interactive transfer.
    # ------------------------------------------------------------------
    async def execute_scheduled_transfer(
        self,
        customer: Customer,
        *,
        sender_account_id,
        receiver_account_number: str,
        amount: Decimal,
        currency: str,
    ) -> Transaction:
        transaction = await self._validate_and_create_pending_transaction(
            customer,
            sender_account_id=sender_account_id,
            receiver_account_number=receiver_account_number,
            amount=amount,
            currency=currency,
        )
        transaction = await self._execute_locked_transfer(transaction)

        write_audit_log_task.delay(
            str(customer.user_id),
            "SCHEDULED_TRANSFER_COMPLETED",
            "transaction",
            str(transaction.id),
            None,
            {"reference_number": transaction.reference_number},
        )
        send_notification_task.delay(
            str(customer.user_id),
            "sms",
            "transfer_completed",
            {"reference_number": transaction.reference_number},
        )
        return transaction

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def list_for_customer(
        self, customer: Customer, *, page: int, page_size: int
    ) -> tuple[list[Transaction], int]:
        accounts = await self._accounts.list_for_customer(customer.id)
        account_ids = [a.id for a in accounts]
        if not account_ids:
            return [], 0
        offset = (page - 1) * page_size
        return await self._transactions.list_for_customer_accounts(
            account_ids, offset=offset, limit=page_size
        )

    async def get_owned_transaction(self, customer: Customer, transaction_id):
        transaction = await self._transactions.get_by_id(transaction_id)
        if transaction is None or not await self._customer_owns_transaction(customer, transaction):
            raise NotFoundError("Transaction not found")
        return transaction

    async def get_ledger_entries(self, transaction_id):
        return await self._ledger_entries.list_for_transaction(transaction_id)

    async def search_by_reference(self, customer: Customer, reference_number: str) -> Transaction:
        transaction = await self._transactions.get_by_reference_number(reference_number)
        if transaction is None or not await self._customer_owns_transaction(customer, transaction):
            raise NotFoundError("Transaction not found")
        return transaction

    async def _get_owned_pending_transaction(self, customer: Customer, transaction_id) -> Transaction:
        transaction = await self._transactions.get_by_id(transaction_id)
        if transaction is None or not await self._customer_owns_transaction(customer, transaction):
            raise NotFoundError("Transaction not found")
        if transaction.status != TransactionStatus.PENDING:
            raise TransactionAlreadyProcessedError()
        return transaction

    async def _customer_owns_transaction(self, customer: Customer, transaction: Transaction) -> bool:
        sender = await self._accounts.get_by_id(transaction.sender_account_id)
        if sender is not None and sender.customer_id == customer.id:
            return True
        receiver = await self._accounts.get_by_id(transaction.receiver_account_id)
        return receiver is not None and receiver.customer_id == customer.id
