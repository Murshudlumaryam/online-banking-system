import uuid

from pydantic import BaseModel, Field


class CreateBeneficiaryRequest(BaseModel):
    beneficiary_account_number: str = Field(min_length=5, max_length=34)
    beneficiary_name: str = Field(min_length=1, max_length=150)
    nickname: str | None = Field(default=None, max_length=100)


class UpdateBeneficiaryRequest(BaseModel):
    beneficiary_name: str | None = Field(default=None, min_length=1, max_length=150)
    nickname: str | None = Field(default=None, max_length=100)


class BeneficiaryResponse(BaseModel):
    id: uuid.UUID
    beneficiary_account_number: str
    beneficiary_name: str
    nickname: str | None

    model_config = {"from_attributes": True}
