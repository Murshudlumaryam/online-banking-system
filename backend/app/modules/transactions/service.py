import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.background_tasks.tasks import dispatch_audit_log, send_notification_task, write_audit_log_task
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
    TransactionNotReversibleError,
)
from app.core.security import generate_otp_code, hash_otp_code, verify_otp_code
from app.modules.accounts.models import AccountStatus
from app.modules.accounts.repository import AccountRepository
from app.modules.audit_logs.actions import AuditAction, AuditStatus
from app.modules.customers.models import Customer
from app.modules.exchange_rates.repository import ExchangeRateRepository
from app.modules.ledger_entries.models import LedgerEntryType
from app.modules.ledger_entries.repository import LedgerEntryRepository
from app.modules.transactions.models import Transaction, TransactionStatus, TransactionType, TransferConfirmation
from app.modules.transactions.repository import (
    TransactionRepository,
    TransferConfirmationRepository,
)
from app.modules.transactions.schemas import TransferMoneyRequest
from app.modules.users.models import User

settings = get_settings()
logger = logging.getLogger("app.otp")


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

        logger.info(
            "TRANSFER_OTP_CREATED",
            extra={
                "transaction_id": str(transaction.id),
                "user_id": str(customer.user_id),
                "expires_in_seconds": expires_in_seconds,
            },
        )

        # The OTP is delivered only through the notification channel(s)
        # configured via OTP_DELIVERY_CHANNEL — it is never included in the
        # HTTP response and never written to logs. Previously hardcoded to
        # "sms" here, which meant a real SMTP-configured email address had
        # no delivery path at all; see app/core/config.py's
        # otp_delivery_channel docstring for the full rationale.
        channel_setting = settings.otp_delivery_channel
        channels = ["email", "sms"] if channel_setting == "both" else [channel_setting]
        for channel in channels:
            logger.info(
                "TRANSFER_OTP_SEND_REQUESTED",
                extra={"transaction_id": str(transaction.id), "channel": channel},
            )
            send_notification_task.delay(
                str(customer.user_id),
                channel,
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

    async def resend_otp(self, customer: Customer, transaction_id: uuid.UUID) -> int:
        """
        Issues a fresh OTP for a PENDING transaction that already has one —
        e.g. the customer's first email/SMS never arrived, or they simply
        waited too long. The old code is invalidated the moment this
        commits (see TransferConfirmationRepository.reissue), and a
        customer already stuck on max failed attempts gets a clean slate
        rather than having to abandon the transfer and start over.

        Rate limiting against resend abuse is handled by the standard
        per-route RateLimitMiddleware (see app/core/middleware.py) applied
        to this endpoint, the same mechanism every other endpoint in this
        API uses — no bespoke resend-specific throttle needed here.
        """
        transaction = await self._get_owned_pending_transaction(customer, transaction_id)
        confirmation = await self._confirmations.get_by_transaction_id(transaction.id)
        if confirmation is None:
            raise NotFoundError("No OTP challenge found for this transaction")

        otp_code = generate_otp_code()
        expires_in_seconds = settings.otp_expire_minutes * 60
        from datetime import datetime, timedelta, timezone

        from app.core import test_otp_store

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes)
        await self._confirmations.reissue(confirmation, otp_code_hash=hash_otp_code(otp_code), expires_at=expires_at)
        await self._session.commit()
        test_otp_store.capture(transaction.id, otp_code)

        logger.info("TRANSFER_OTP_RESENT", extra={"transaction_id": str(transaction.id)})

        channel_setting = settings.otp_delivery_channel
        channels = ["email", "sms"] if channel_setting == "both" else [channel_setting]
        for channel in channels:
            logger.info(
                "TRANSFER_OTP_SEND_REQUESTED",
                extra={"transaction_id": str(transaction.id), "channel": channel},
            )
            send_notification_task.delay(
                str(customer.user_id),
                channel,
                "transfer_otp",
                {"otp_code": otp_code, "reference_number": transaction.reference_number},
            )
        return expires_in_seconds

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
            logger.warning(
                "TRANSFER_OTP_VERIFY_FAILED",
                extra={"transaction_id": str(transaction_id), "reason": "no_challenge_found"},
            )
            raise NotFoundError("No OTP challenge found for this transaction")

        if self._confirmations.is_expired(confirmation):
            await self._transactions.mark_failed(transaction, "OTP expired")
            await self._session.commit()
            from app.core.metrics import transfers_total

            logger.info("TRANSFER_OTP_EXPIRED", extra={"transaction_id": str(transaction.id)})
            dispatch_audit_log(
                str(customer.user_id), AuditAction.TRANSFER_FAILED, "transaction", str(transaction.id),
                None, {"reference_number": transaction.reference_number, "reason": "OTP expired"},
                status=AuditStatus.FAILED.value,
            )
            transfers_total.labels(outcome="failed").inc()
            raise OtpExpiredError()

        if self._confirmations.attempts_exhausted(confirmation):
            await self._transactions.mark_failed(transaction, "Too many invalid OTP attempts")
            await self._session.commit()
            from app.core.metrics import transfers_total

            logger.warning(
                "TRANSFER_OTP_MAX_ATTEMPTS_EXCEEDED", extra={"transaction_id": str(transaction.id)}
            )
            dispatch_audit_log(
                str(customer.user_id), AuditAction.TRANSFER_FAILED, "transaction", str(transaction.id),
                None, {"reference_number": transaction.reference_number, "reason": "too many invalid OTP attempts"},
                status=AuditStatus.FAILED.value,
            )
            transfers_total.labels(outcome="otp_invalid").inc()
            raise TooManyOtpAttemptsError()

        if not verify_otp_code(otp_code, confirmation.otp_code_hash):
            await self._confirmations.register_failed_attempt(confirmation)
            attempts_remaining = confirmation.max_attempts - confirmation.attempts
            from app.core.metrics import transfers_total

            logger.info(
                "TRANSFER_OTP_INVALID",
                extra={"transaction_id": str(transaction.id), "attempts_remaining": attempts_remaining},
            )
            if attempts_remaining <= 0:
                await self._transactions.mark_failed(transaction, "Too many invalid OTP attempts")
                await self._session.commit()
                logger.warning(
                    "TRANSFER_OTP_MAX_ATTEMPTS_EXCEEDED", extra={"transaction_id": str(transaction.id)}
                )
                dispatch_audit_log(
                    str(customer.user_id), AuditAction.TRANSFER_FAILED, "transaction", str(transaction.id),
                    None,
                    {"reference_number": transaction.reference_number, "reason": "too many invalid OTP attempts"},
                    status=AuditStatus.FAILED.value,
                )
                transfers_total.labels(outcome="otp_invalid").inc()
                raise TooManyOtpAttemptsError()
            await self._session.commit()
            transfers_total.labels(outcome="otp_invalid").inc()
            raise InvalidOtpError(attempts_remaining)

        logger.info("TRANSFER_OTP_VERIFIED", extra={"transaction_id": str(transaction.id)})
        transaction = await self._execute_locked_transfer(transaction, confirmation=confirmation)
        logger.info("TRANSFER_COMPLETED", extra={"transaction_id": str(transaction.id)})

        write_audit_log_task.delay(
            str(customer.user_id),
            "TRANSFER_COMPLETED",
            "transaction",
            str(transaction.id),
            None,
            {"reference_number": transaction.reference_number},
        )
        completion_channel = "sms" if settings.otp_delivery_channel == "sms" else "email"
        send_notification_task.delay(
            str(customer.user_id),
            completion_channel,
            "transfer_completed",
            {"reference_number": transaction.reference_number},
        )
        return transaction

    async def _execute_locked_transfer(
        self, transaction: Transaction, *, confirmation: TransferConfirmation | None = None
    ) -> Transaction:
        """
        Atomically locks the transaction row itself first (re-checking its
        status under that lock — see TransactionRepository.get_for_update's
        docstring for why this is the actual fix for the double-confirmation
        race), then locks both accounts (ordered by id to prevent
        deadlocks), moves the money, and writes balanced ledger entries.

        `confirmation` is optional: interactive OTP transfers pass their
        TransferConfirmation so it gets marked verified in the SAME commit
        as the balance/ledger changes (no separate trailing commit — either
        the whole confirmation succeeds together, or none of it does).
        Scheduled/recurring payments have no OTP step and pass nothing.

        On any domain-rule violation discovered under lock (account state
        changed since the transaction row was created, or the transaction
        was already resolved by a concurrent request), rolls back and marks
        the transaction FAILED — unless a concurrent request already
        resolved it, in which case that outcome is preserved rather than
        overwritten, and TransactionAlreadyProcessedError is raised instead.
        """
        try:
            locked_transaction = await self._transactions.get_for_update(transaction.id)
            if locked_transaction is None:
                raise NotFoundError("Transaction not found")
            if locked_transaction.status != TransactionStatus.PENDING:
                # Another request already resolved this transaction while we
                # were waiting for the lock — never re-process or overwrite it.
                raise TransactionAlreadyProcessedError()

            # This method only ever runs for TRANSFER-type transactions
            # (confirm_transfer and execute_scheduled_transfer) — the DB's
            # ck_transactions_accounts_match_type CHECK constraint guarantees
            # both are set for that type. DEPOSIT/WITHDRAWAL (single-sided,
            # one of these legitimately null) go through TransactionService
            # .deposit/.withdraw instead, never through here.
            assert locked_transaction.sender_account_id is not None
            assert locked_transaction.receiver_account_id is not None

            locked_accounts = await self._accounts.get_two_for_update(
                locked_transaction.sender_account_id, locked_transaction.receiver_account_id
            )
            sender = locked_accounts[locked_transaction.sender_account_id]
            receiver = locked_accounts[locked_transaction.receiver_account_id]

            if sender.status != AccountStatus.ACTIVE:
                raise AccountNotActiveError(which="sender account")
            if receiver.status != AccountStatus.ACTIVE:
                raise AccountNotActiveError(which="receiver account")
            if sender.balance < locked_transaction.amount:
                raise InsufficientBalanceError()

            credit_amount = (
                locked_transaction.converted_amount
                if locked_transaction.converted_amount is not None
                else locked_transaction.amount
            )

            sender_balance_before = sender.balance
            sender.balance = sender.balance - locked_transaction.amount
            sender.version += 1

            receiver_balance_before = receiver.balance
            receiver.balance = receiver.balance + credit_amount
            receiver.version += 1

            self._ledger_entries.create(
                transaction_id=locked_transaction.id,
                account_id=sender.id,
                entry_type=LedgerEntryType.DEBIT,
                amount=locked_transaction.amount,
                currency=sender.currency,
                balance_before=sender_balance_before,
                balance_after=sender.balance,
            )
            self._ledger_entries.create(
                transaction_id=locked_transaction.id,
                account_id=receiver.id,
                entry_type=LedgerEntryType.CREDIT,
                amount=credit_amount,
                currency=receiver.currency,
                balance_before=receiver_balance_before,
                balance_after=receiver.balance,
            )

            await self._transactions.mark_success(locked_transaction)
            if confirmation is not None:
                locked_transaction.otp_verified = True
                await self._confirmations.mark_verified(confirmation)

            await self._session.commit()
            from app.core.metrics import transfers_total

            transfers_total.labels(outcome="success").inc()
            return locked_transaction
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
        """
        Used specifically by confirm_transfer and resend_otp — deliberately
        stricter than _customer_owns_transaction (sender OR receiver, used
        for read-only access like viewing/searching a transaction). Only
        the SENDER authorized this transfer and is the one who received
        the OTP in the first place; a receiver has no legitimate reason to
        confirm or resend it.
        """
        transaction = await self._transactions.get_by_id(transaction_id)
        if transaction is None or not await self._customer_is_sender(customer, transaction):
            # Deliberately the same NotFoundError whether the transaction
            # genuinely doesn't exist, belongs to someone else entirely, or
            # exists and belongs to this customer only as its *receiver*
            # — never confirm to the caller which case it was (see
            # app.core.exceptions' other "don't reveal existence" uses,
            # e.g. login's INVALID_CREDENTIALS for both "no such user" and
            # "wrong password").
            logger.warning(
                "TRANSFER_OTP_VERIFY_FAILED",
                extra={
                    "transaction_id": str(transaction_id),
                    "user_id": str(customer.user_id),
                    "reason": "not_found_or_not_sender",
                },
            )
            raise NotFoundError("Transaction not found")
        if transaction.status != TransactionStatus.PENDING:
            logger.info(
                "TRANSFER_OTP_VERIFY_FAILED",
                extra={
                    "transaction_id": str(transaction_id),
                    "reason": "already_processed",
                    "status": transaction.status.value,
                },
            )
            raise TransactionAlreadyProcessedError()
        return transaction

    async def _customer_owns_transaction(self, customer: Customer, transaction: Transaction) -> bool:
        if transaction.sender_account_id is not None:
            sender = await self._accounts.get_by_id(transaction.sender_account_id)
            if sender is not None and sender.customer_id == customer.id:
                return True
        if transaction.receiver_account_id is not None:
            receiver = await self._accounts.get_by_id(transaction.receiver_account_id)
            if receiver is not None and receiver.customer_id == customer.id:
                return True
        return False

    async def _customer_is_sender(self, customer: Customer, transaction: Transaction) -> bool:
        """Stricter than _customer_owns_transaction: True only if `customer`
        is the account that money is leaving, never the receiver."""
        if transaction.sender_account_id is None:
            return False
        sender = await self._accounts.get_by_id(transaction.sender_account_id)
        return sender is not None and sender.customer_id == customer.id

    async def deposit(
        self,
        *,
        account_id: uuid.UUID,
        amount: Decimal,
        currency: str,
        note: str | None,
        performed_by_user_id: uuid.UUID,
    ) -> Transaction:
        """
        Credits `account_id` with money entering this closed-loop system
        from outside it (e.g. cash handed to a teller, an incoming external
        wire) — there is no "sender account" within the system, unlike a
        transfer. Admin-only (see app/modules/admin/router.py): this system
        has no real payment-rail integration, so an admin action is the
        stand-in for whatever real-world channel actually brought the money
        in. Atomic: account lock, balance update, single ledger entry, and
        the transaction's SUCCESS status all commit together, mirroring the
        same discipline as _execute_locked_transfer.
        """
        try:
            account = await self._accounts.get_one_for_update(account_id)
            if account is None:
                raise NotFoundError("Account not found")
            if account.status != AccountStatus.ACTIVE:
                raise AccountNotActiveError(which="account")
            if account.currency != currency:
                raise CurrencyMismatchError(expected=account.currency, provided=currency)

            transaction = self._transactions.create(
                sender_account_id=None,
                receiver_account_id=account.id,
                amount=amount,
                currency=currency,
                exchange_rate_id=None,
                converted_amount=None,
                transaction_type=TransactionType.DEPOSIT,
                note=note,
                performed_by_user_id=performed_by_user_id,
            )
            await self._session.flush()

            balance_before = account.balance
            account.balance = account.balance + amount
            account.version += 1

            self._ledger_entries.create(
                transaction_id=transaction.id,
                account_id=account.id,
                entry_type=LedgerEntryType.CREDIT,
                amount=amount,
                currency=currency,
                balance_before=balance_before,
                balance_after=account.balance,
            )

            await self._transactions.mark_success(transaction)
            await self._session.commit()

            write_audit_log_task.delay(
                str(performed_by_user_id), "DEPOSIT", "account", str(account.id), None, None
            )
            return transaction
        except DomainError:
            await self._session.rollback()
            raise

    async def withdraw(
        self,
        *,
        account_id: uuid.UUID,
        amount: Decimal,
        currency: str,
        note: str | None,
        performed_by_user_id: uuid.UUID,
    ) -> Transaction:
        """The withdrawal mirror of `deposit` — debits `account_id` for
        money leaving this closed-loop system (e.g. cash paid out at a
        branch). See `deposit`'s docstring for the shared design notes."""
        try:
            account = await self._accounts.get_one_for_update(account_id)
            if account is None:
                raise NotFoundError("Account not found")
            if account.status != AccountStatus.ACTIVE:
                raise AccountNotActiveError(which="account")
            if account.currency != currency:
                raise CurrencyMismatchError(expected=account.currency, provided=currency)
            if account.balance < amount:
                raise InsufficientBalanceError()

            transaction = self._transactions.create(
                sender_account_id=account.id,
                receiver_account_id=None,
                amount=amount,
                currency=currency,
                exchange_rate_id=None,
                converted_amount=None,
                transaction_type=TransactionType.WITHDRAWAL,
                note=note,
                performed_by_user_id=performed_by_user_id,
            )
            await self._session.flush()

            balance_before = account.balance
            account.balance = account.balance - amount
            account.version += 1

            self._ledger_entries.create(
                transaction_id=transaction.id,
                account_id=account.id,
                entry_type=LedgerEntryType.DEBIT,
                amount=amount,
                currency=currency,
                balance_before=balance_before,
                balance_after=account.balance,
            )

            await self._transactions.mark_success(transaction)
            await self._session.commit()

            write_audit_log_task.delay(
                str(performed_by_user_id), "WITHDRAWAL", "account", str(account.id), None, None
            )
            return transaction
        except DomainError:
            await self._session.rollback()
            raise

    async def reverse_transaction(
        self, admin_user: User, transaction_id: uuid.UUID, reason: str
    ) -> Transaction:
        """
        Admin-only. Creates a brand-new transaction that moves money back
        the opposite way from a completed one, and marks the original
        REVERSED. Deliberately does NOT edit the original transaction's
        amount or its ledger rows — ledger entries are append-only (see
        LedgerEntry's docstring); a reversal is a new, independently
        auditable movement of money, not a correction of history.

        Reversal direction depends on the original's type:
        - TRANSFER sender->receiver reverses as receiver->sender.
        - DEPOSIT (money entered from outside) reverses as a WITHDRAWAL
          from the account it credited.
        - WITHDRAWAL reverses as a DEPOSIT back into the account it debited.

        Uses the same lock-the-transaction-row-first-and-recheck-status
        discipline as _execute_locked_transfer/deposit/withdraw — see those
        docstrings and TransactionRepository.get_for_update's docstring for
        why this specific ordering is what actually prevents a double
        -reversal race, not just an application-level pre-check.
        """
        try:
            original = await self._transactions.get_for_update(transaction_id)
            if original is None:
                raise NotFoundError("Transaction not found")
            if original.status != TransactionStatus.SUCCESS:
                raise TransactionNotReversibleError(
                    f"only a SUCCESS transaction can be reversed (this one is {original.status.value})"
                )

            existing_reversal = await self._transactions.get_by_reversal_of(original.id)
            if existing_reversal is not None:
                raise TransactionNotReversibleError("this transaction has already been reversed once")

            if original.transaction_type == TransactionType.TRANSFER:
                assert original.sender_account_id is not None
                assert original.receiver_account_id is not None
                locked = await self._accounts.get_two_for_update(
                    original.sender_account_id, original.receiver_account_id
                )
                reversal_sender = locked[original.receiver_account_id]
                reversal_receiver = locked[original.sender_account_id]
                new_sender_id: uuid.UUID | None = reversal_sender.id
                new_receiver_id: uuid.UUID | None = reversal_receiver.id
                new_type = TransactionType.TRANSFER
                if reversal_sender.status != AccountStatus.ACTIVE:
                    raise AccountNotActiveError(which="original receiver's account")
                if reversal_receiver.status != AccountStatus.ACTIVE:
                    raise AccountNotActiveError(which="original sender's account")
                if reversal_sender.balance < original.amount:
                    raise InsufficientBalanceError()
            elif original.transaction_type == TransactionType.DEPOSIT:
                assert original.receiver_account_id is not None
                account = await self._accounts.get_one_for_update(original.receiver_account_id)
                assert account is not None
                if account.status != AccountStatus.ACTIVE:
                    raise AccountNotActiveError(which="account")
                if account.balance < original.amount:
                    raise InsufficientBalanceError()
                new_sender_id, new_receiver_id = account.id, None
                new_type = TransactionType.WITHDRAWAL
            elif original.transaction_type == TransactionType.WITHDRAWAL:
                assert original.sender_account_id is not None
                account = await self._accounts.get_one_for_update(original.sender_account_id)
                assert account is not None
                if account.status != AccountStatus.ACTIVE:
                    raise AccountNotActiveError(which="account")
                new_sender_id, new_receiver_id = None, account.id
                new_type = TransactionType.DEPOSIT
            else:
                raise TransactionNotReversibleError(f"unknown transaction type {original.transaction_type}")

            reversal = self._transactions.create(
                sender_account_id=new_sender_id,
                receiver_account_id=new_receiver_id,
                amount=original.amount,
                currency=original.currency,
                exchange_rate_id=None,
                converted_amount=None,
                transaction_type=new_type,
                note=f"Reversal of {original.reference_number}: {reason}",
                performed_by_user_id=admin_user.id,
            )
            reversal.reversal_of_transaction_id = original.id
            await self._session.flush()

            if new_sender_id is not None:
                sender_account = await self._accounts.get_one_for_update(new_sender_id)
                assert sender_account is not None
                sender_balance_before = sender_account.balance
                sender_account.balance = sender_account.balance - original.amount
                sender_account.version += 1
                self._ledger_entries.create(
                    transaction_id=reversal.id, account_id=sender_account.id,
                    entry_type=LedgerEntryType.DEBIT, amount=original.amount, currency=original.currency,
                    balance_before=sender_balance_before, balance_after=sender_account.balance,
                )
            if new_receiver_id is not None:
                receiver_account = await self._accounts.get_one_for_update(new_receiver_id)
                assert receiver_account is not None
                receiver_balance_before = receiver_account.balance
                receiver_account.balance = receiver_account.balance + original.amount
                receiver_account.version += 1
                self._ledger_entries.create(
                    transaction_id=reversal.id, account_id=receiver_account.id,
                    entry_type=LedgerEntryType.CREDIT, amount=original.amount, currency=original.currency,
                    balance_before=receiver_balance_before, balance_after=receiver_account.balance,
                )

            await self._transactions.mark_success(reversal)
            original.status = TransactionStatus.REVERSED
            await self._transactions.save(original)
            await self._session.commit()

            write_audit_log_task.delay(
                str(admin_user.id), "ADMIN_TRANSACTION_REVERSED", "transaction", str(original.id), None,
                {"reversal_transaction_id": str(reversal.id), "reason": reason},
            )
            return reversal
        except DomainError:
            await self._session.rollback()
            raise
