from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.background_tasks.tasks import write_audit_log_task
from app.core.exceptions import NotFoundError
from app.modules.accounts.repository import AccountRepository
from app.modules.beneficiaries.models import Beneficiary, BeneficiaryStatus
from app.modules.beneficiaries.repository import BeneficiaryRepository
from app.modules.beneficiaries.schemas import (
    CreateBeneficiaryRequest,
    UpdateBeneficiaryRequest,
)
from app.modules.customers.models import Customer


class BeneficiaryService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._beneficiaries = BeneficiaryRepository(session)
        self._accounts = AccountRepository(session)

    async def create(self, customer: Customer, payload: CreateBeneficiaryRequest) -> Beneficiary:
        target_account = await self._accounts.get_by_account_number(payload.beneficiary_account_number)
        if target_account is None:
            raise NotFoundError("No account exists with this account number")

        beneficiary = self._beneficiaries.create(
            customer_id=customer.id,
            beneficiary_account_number=payload.beneficiary_account_number,
            beneficiary_name=payload.beneficiary_name,
            nickname=payload.nickname,
        )
        await self._session.commit()

        write_audit_log_task.delay(
            str(customer.user_id), "BENEFICIARY_ADDED", "beneficiary", str(beneficiary.id), None, None
        )
        return beneficiary

    async def update(
        self, beneficiary: Beneficiary, payload: UpdateBeneficiaryRequest
    ) -> Beneficiary:
        if payload.beneficiary_name is not None:
            beneficiary.beneficiary_name = payload.beneficiary_name
        if payload.nickname is not None:
            beneficiary.nickname = payload.nickname

        await self._beneficiaries.save(beneficiary)
        await self._session.commit()
        return beneficiary

    async def delete(self, beneficiary: Beneficiary) -> None:
        beneficiary.status = BeneficiaryStatus.DELETED
        beneficiary.deleted_at = datetime.now(timezone.utc)
        await self._beneficiaries.save(beneficiary)
        await self._session.commit()
