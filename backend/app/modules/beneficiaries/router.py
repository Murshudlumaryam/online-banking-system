from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.beneficiaries.dependencies import get_owned_beneficiary
from app.modules.beneficiaries.models import Beneficiary
from app.modules.beneficiaries.repository import BeneficiaryRepository
from app.modules.beneficiaries.schemas import (
    BeneficiaryResponse,
    CreateBeneficiaryRequest,
    UpdateBeneficiaryRequest,
)
from app.modules.beneficiaries.service import BeneficiaryService
from app.modules.customers.dependencies import get_current_customer
from app.modules.customers.models import Customer

router = APIRouter(prefix="/api/v1/beneficiaries", tags=["beneficiaries"])


@router.get("", response_model=list[BeneficiaryResponse], summary="List saved beneficiaries")
async def list_beneficiaries(
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> list[BeneficiaryResponse]:
    beneficiaries = await BeneficiaryRepository(session).list_for_customer(customer.id)
    return [BeneficiaryResponse.model_validate(b) for b in beneficiaries]


@router.post(
    "",
    response_model=BeneficiaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a new beneficiary",
)
async def create_beneficiary(
    payload: CreateBeneficiaryRequest,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> BeneficiaryResponse:
    service = BeneficiaryService(session)
    beneficiary = await service.create(customer, payload)
    return BeneficiaryResponse.model_validate(beneficiary)


@router.patch(
    "/{beneficiary_id}", response_model=BeneficiaryResponse, summary="Update a saved beneficiary"
)
async def update_beneficiary(
    payload: UpdateBeneficiaryRequest,
    beneficiary: Beneficiary = Depends(get_owned_beneficiary),
    session: AsyncSession = Depends(get_db),
) -> BeneficiaryResponse:
    service = BeneficiaryService(session)
    updated = await service.update(beneficiary, payload)
    return BeneficiaryResponse.model_validate(updated)


@router.delete(
    "/{beneficiary_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a saved beneficiary"
)
async def delete_beneficiary(
    beneficiary: Beneficiary = Depends(get_owned_beneficiary),
    session: AsyncSession = Depends(get_db),
) -> None:
    service = BeneficiaryService(session)
    await service.delete(beneficiary)
