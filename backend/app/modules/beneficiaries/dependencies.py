import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.beneficiaries.models import Beneficiary
from app.modules.beneficiaries.repository import BeneficiaryRepository
from app.modules.customers.dependencies import get_current_customer
from app.modules.customers.models import Customer


async def get_owned_beneficiary(
    beneficiary_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> Beneficiary:
    beneficiary = await BeneficiaryRepository(session).get_by_id(beneficiary_id)
    if beneficiary is None or beneficiary.customer_id != customer.id:
        raise NotFoundError("Beneficiary not found")
    return beneficiary
