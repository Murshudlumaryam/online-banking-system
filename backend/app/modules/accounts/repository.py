import secrets
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounts.models import Account, AccountStatus


def generate_account_number() -> str:
    # IBAN-like synthetic identifier: AZ + 2 check digits + 20 alnum chars
    return f"AZ{secrets.randbelow(100):02d}BANK{secrets.token_hex(9).upper()}"[:28]


class AccountRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, account_id: uuid.UUID) -> Account | None:
        result = await self._session.execute(select(Account).where(Account.id == account_id))
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, account_id: uuid.UUID) -> Account | None:
        result = await self._session.execute(
            select(Account).where(Account.id == account_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_two_for_update(
        self, account_id_1: uuid.UUID, account_id_2: uuid.UUID
    ) -> dict[uuid.UUID, Account]:
        """
        Locks both accounts with SELECT ... FOR UPDATE, always ordered by id
        regardless of the order the ids are passed in. This is the deadlock
        -prevention rule: two concurrent transfers in opposite directions
        between the same two accounts will always attempt to acquire locks
        in the same order, so one waits for the other instead of both
        deadlocking.
        """
        ordered_ids = sorted([account_id_1, account_id_2], key=str)
        result = await self._session.execute(
            select(Account).where(Account.id.in_(ordered_ids)).order_by(Account.id).with_for_update()
        )
        accounts = {account.id: account for account in result.scalars().all()}
        return accounts

    async def get_by_account_number(self, account_number: str) -> Account | None:
        result = await self._session.execute(
            select(Account).where(Account.account_number == account_number)
        )
        return result.scalar_one_or_none()

    async def list_for_customer(self, customer_id: uuid.UUID) -> list[Account]:
        result = await self._session.execute(
            select(Account).where(Account.customer_id == customer_id).order_by(Account.created_at)
        )
        return list(result.scalars().all())

    async def total_balance_by_currency(self, customer_id: uuid.UUID) -> dict[str, Decimal]:
        accounts = await self.list_for_customer(customer_id)
        totals: dict[str, Decimal] = {}
        for account in accounts:
            if account.status == AccountStatus.CLOSED:
                continue
            totals[account.currency] = totals.get(account.currency, Decimal("0")) + account.balance
        return totals

    async def list_all(
        self, *, offset: int, limit: int, status: AccountStatus | None = None
    ) -> tuple[list[Account], int]:
        query = select(Account)
        if status is not None:
            query = query.where(Account.status == status)

        count_result = await self._session.execute(query.with_only_columns(Account.id))
        total = len(count_result.all())

        result = await self._session.execute(
            query.order_by(Account.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    def create(
        self,
        *,
        customer_id: uuid.UUID,
        account_number: str,
        account_type: str,
        currency: str,
        status: AccountStatus = AccountStatus.PENDING,
    ) -> Account:
        account = Account(
            customer_id=customer_id,
            account_number=account_number,
            account_type=account_type,
            currency=currency,
            status=status,
        )
        self._session.add(account)
        return account

    async def save(self, account: Account) -> None:
        self._session.add(account)
        await self._session.flush()
