import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    resource_type: str | None
    resource_id: uuid.UUID | None
    status: str | None
    ip_address: str | None
    user_agent: str | None
    request_id: str | None
    log_metadata: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("ip_address", mode="before")
    @classmethod
    def coerce_ip_address(cls, value):
        # SQLAlchemy's postgresql.INET column returns ipaddress.IPv4Address /
        # IPv6Address objects, not str — coerce here rather than at every
        # call site.
        return str(value) if value is not None else None
