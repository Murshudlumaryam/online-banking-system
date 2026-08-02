from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.auth.dependencies import require_customer
from app.modules.customers.models import Customer
from app.modules.customers.repository import CustomerRepository
from app.modules.users.models import User


async def get_current_customer(
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db),
) -> Customer:
    customer = await CustomerRepository(session).get_by_user_id(current_user.id)
    if customer is None:
        # Should not happen in practice — a CUSTOMER-role user is always
        # created together with a Customer row at registration time.
        raise NotFoundError("Customer profile not found for this account")
    return customer
