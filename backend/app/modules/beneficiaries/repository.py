import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.beneficiaries.models import Beneficiary, BeneficiaryStatus


class BeneficiaryRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, beneficiary_id: uuid.UUID) -> Beneficiary | None:
        result = await self._session.execute(
            select(Beneficiary).where(
                Beneficiary.id == beneficiary_id, Beneficiary.status == BeneficiaryStatus.ACTIVE
            )
        )
        return result.scalar_one_or_none()

    async def list_for_customer(self, customer_id: uuid.UUID) -> list[Beneficiary]:
        result = await self._session.execute(
            select(Beneficiary)
            .where(Beneficiary.customer_id == customer_id, Beneficiary.status == BeneficiaryStatus.ACTIVE)
            .order_by(Beneficiary.created_at.desc())
        )
        return list(result.scalars().all())

    def create(
        self,
        *,
        customer_id: uuid.UUID,
        beneficiary_account_number: str,
        beneficiary_name: str,
        nickname: str | None = None,
    ) -> Beneficiary:
        beneficiary = Beneficiary(
            customer_id=customer_id,
            beneficiary_account_number=beneficiary_account_number,
            beneficiary_name=beneficiary_name,
            nickname=nickname,
        )
        self._session.add(beneficiary)
        return beneficiary

    async def save(self, beneficiary: Beneficiary) -> None:
        self._session.add(beneficiary)
        await self._session.flush()
