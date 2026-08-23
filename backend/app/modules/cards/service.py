import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.background_tasks.tasks import write_audit_log_task
from app.core.exceptions import (
    AccountNotActiveError,
    ConflictError,
    CurrencyMismatchError,
    DomainError,
    InsufficientBalanceError,
)
from app.modules.accounts.models import AccountStatus
from app.modules.accounts.repository import AccountRepository
from app.modules.cards.models import Card, CardStatus
from app.modules.cards.repository import CardRepository
from app.modules.customers.models import Customer
from app.modules.ledger_entries.models import LedgerEntryType
from app.modules.ledger_entries.repository import LedgerEntryRepository
from app.modules.transactions.models import Transaction, TransactionType
from app.modules.transactions.repository import TransactionRepository


class CardService:
    """Customer-facing card operations. Admin-initiated card actions
    (issue, admin-block, delete) live in
    app.modules.admin.service.AdminService — this module is specifically
    the subset a customer can do to their own card without an admin in
    the loop."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._cards = CardRepository(session)
        self._accounts = AccountRepository(session)
        self._transactions = TransactionRepository(session)
        self._ledger_entries = LedgerEntryRepository(session)

    async def block_own_card(self, customer: Customer, card: Card) -> Card:
        """Self-service equivalent of a "report lost/stolen card" call to a
        real bank's hotline. Ownership of `card` is verified by the caller
        (see app.modules.cards.dependencies.get_owned_card) before this is
        reached — this method only handles the state transition itself.
        """
        if card.status == CardStatus.BLOCKED:
            raise ConflictError("This card is already blocked")
        if card.status == CardStatus.EXPIRED:
            raise ConflictError("This card has expired and cannot be blocked")

        card.status = CardStatus.BLOCKED
        card.blocked_at = datetime.now(timezone.utc)
        await self._cards.save(card)
        await self._session.commit()

        write_audit_log_task.delay(
            str(customer.user_id), "CUSTOMER_CARD_BLOCKED", "card", str(card.id), None, None
        )
        return card

    async def pay_with_card(
        self, customer: Customer, card_id: uuid.UUID, *, amount: Decimal, currency: str, merchant_name: str
    ) -> Transaction:
        """
        Simulates a card purchase (a POS/online charge) — debits the
        account behind the card by `amount`, tagged as CARD_PAYMENT rather
        than WITHDRAWAL so it's distinguishable in statements/reporting
        even though both are single-sided debits. There is no real card
        network here (no acquirer, no merchant settlement) — this is the
        closed-loop simulation's stand-in for "the customer bought
        something with this card".

        Ownership of the card is verified by the caller (see
        app.modules.cards.dependencies.get_owned_card), same as
        block_own_card. Uses the identical lock-the-row-first discipline
        as TransactionService.deposit/withdraw: the card itself is locked
        first (so it can't be blocked/deleted mid-payment by a concurrent
        request), then the account.
        """
        try:
            locked_card = await self._cards.get_one_for_update(card_id)
            if locked_card is None:
                raise ConflictError("Card not found")
            if locked_card.status != CardStatus.ACTIVE:
                raise ConflictError(f"This card is {locked_card.status.value.lower()} and cannot be charged")

            account = await self._accounts.get_one_for_update(locked_card.account_id)
            if account is None:
                raise ConflictError("The account behind this card no longer exists")
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
                transaction_type=TransactionType.CARD_PAYMENT,
                note=merchant_name,
                card_id=locked_card.id,
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
                str(customer.user_id), "CARD_PAYMENT", "card", str(locked_card.id), None,
                {"merchant": merchant_name, "amount": str(amount), "currency": currency},
            )
            return transaction
        except DomainError:
            await self._session.rollback()
            raise
