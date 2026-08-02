from sqlalchemy.ext.asyncio import AsyncSession

from app.background_tasks.tasks import write_audit_log_task
from app.modules.accounts.repository import AccountRepository
from app.modules.accounts.schemas import AccountResponse
from app.modules.customers.models import Customer
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schemas import (
    CurrencyBalance,
    DashboardResponse,
    UpdateCustomerProfileRequest,
)


class CustomerService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._customers = CustomerRepository(session)
        self._accounts = AccountRepository(session)

    async def update_profile(
        self, customer: Customer, payload: UpdateCustomerProfileRequest
    ) -> Customer:
        if payload.phone_number is not None:
            customer.phone_number = payload.phone_number
        if payload.address is not None:
            customer.address = payload.address

        await self._customers.save(customer)
        await self._session.commit()

        write_audit_log_task.delay(
            str(customer.user_id), "PROFILE_UPDATED", "customer", str(customer.id), None, None
        )
        return customer

    async def get_dashboard(self, customer: Customer) -> DashboardResponse:
        accounts = await self._accounts.list_for_customer(customer.id)
        totals = await self._accounts.total_balance_by_currency(customer.id)

        return DashboardResponse(
            customer_number=customer.customer_number,
            full_name=f"{customer.first_name} {customer.last_name}",
            total_accounts=len(accounts),
            balances_by_currency=[
                CurrencyBalance(currency=currency, total_balance=total)
                for currency, total in totals.items()
            ],
            accounts=[AccountResponse.model_validate(a) for a in accounts],
        )
