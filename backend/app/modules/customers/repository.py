import secrets
import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer, CustomerStatus


def _generate_customer_number() -> str:
    # 10-digit numeric identifier, e.g. CUS-4839201005
    return f"CUS-{secrets.randbelow(10**10):010d}"


class CustomerRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, customer_id: uuid.UUID) -> Customer | None:
        result = await self._session.execute(
            select(Customer).where(Customer.id == customer_id, Customer.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_all(
        self, *, offset: int, limit: int, status: CustomerStatus | None = None, search: str | None = None
    ) -> tuple[list[Customer], int]:
        from app.modules.users.models import User

        query = select(Customer).where(Customer.deleted_at.is_(None))
        if status is not None:
            query = query.where(Customer.status == status)
        if search:
            # Joins Customer -> User so a single search box can match name,
            # phone, national ID, customer number, OR email in one query —
            # an admin looking someone up rarely knows which field they have.
            pattern = f"%{search}%"
            query = query.join(User, User.id == Customer.user_id).where(
                or_(
                    Customer.first_name.ilike(pattern),
                    Customer.last_name.ilike(pattern),
                    Customer.phone_number.ilike(pattern),
                    Customer.national_id.ilike(pattern),
                    Customer.customer_number.ilike(pattern),
                    User.email.ilike(pattern),
                )
            )

        count_result = await self._session.execute(query.with_only_columns(Customer.id))
        total = len(count_result.all())

        result = await self._session.execute(
            query.order_by(Customer.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_by_user_id(self, user_id: uuid.UUID) -> Customer | None:
        result = await self._session.execute(
            select(Customer).where(Customer.user_id == user_id, Customer.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def national_id_exists(self, national_id: str) -> bool:
        if not national_id:
            return False
        result = await self._session.execute(
            select(Customer).where(Customer.national_id == national_id)
        )
        return result.scalar_one_or_none() is not None

    def create(
        self,
        *,
        user_id: uuid.UUID,
        first_name: str,
        last_name: str,
        date_of_birth: date,
        phone_number: str,
        address: str | None = None,
        national_id: str | None = None,
    ) -> Customer:
        customer = Customer(
            user_id=user_id,
            customer_number=_generate_customer_number(),
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            phone_number=phone_number,
            address=address,
            national_id=national_id,
        )
        self._session.add(customer)
        return customer

    async def save(self, customer: Customer) -> None:
        self._session.add(customer)
        await self._session.flush()
