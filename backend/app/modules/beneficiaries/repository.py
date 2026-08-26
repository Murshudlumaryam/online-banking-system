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

    async def list_all(self, *, offset: int, limit: int) -> tuple[list[Beneficiary], int]:
        """Admin-facing: every customer's beneficiaries, not scoped to one
        customer. See app/modules/admin/router.py's GET /admin/beneficiaries."""
        query = select(Beneficiary).where(Beneficiary.status == BeneficiaryStatus.ACTIVE)

        count_result = await self._session.execute(query.with_only_columns(Beneficiary.id))
        total = len(count_result.all())

        result = await self._session.execute(
            query.order_by(Beneficiary.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

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

    async def get_by_id_including_deleted(self, beneficiary_id: uuid.UUID) -> Beneficiary | None:
        result = await self._session.execute(select(Beneficiary).where(Beneficiary.id == beneficiary_id))
        return result.scalar_one_or_none()

    async def restore(self, beneficiary: Beneficiary) -> None:
        beneficiary.status = BeneficiaryStatus.ACTIVE
        beneficiary.deleted_at = None
        self._session.add(beneficiary)
        await self._session.flush()

    async def list_deleted(self, *, offset: int, limit: int) -> tuple[list[Beneficiary], int]:
        query = select(Beneficiary).where(Beneficiary.status == BeneficiaryStatus.DELETED)

        count_result = await self._session.execute(query.with_only_columns(Beneficiary.id))
        total = len(count_result.all())

        result = await self._session.execute(
            query.order_by(Beneficiary.deleted_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total
