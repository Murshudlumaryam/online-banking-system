import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.accounts.models import Account
from app.modules.accounts.repository import AccountRepository
from app.modules.customers.dependencies import get_current_customer
from app.modules.customers.models import Customer


async def get_owned_account(
    account_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> Account:
    account = await AccountRepository(session).get_by_id(account_id)

    # Deliberately the same NotFoundError whether the account doesn't exist
    # at all or belongs to someone else — never confirm the existence of a
    # resource that isn't the caller's.
    if account is None or account.customer_id != customer.id:
        raise NotFoundError("Account not found")

    return account
