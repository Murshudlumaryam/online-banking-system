import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit_logs.models import AuditLog


class AuditLogRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(
        self,
        *,
        offset: int,
        limit: int,
        user_id: uuid.UUID | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        status: str | None = None,
        request_id: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> tuple[list[AuditLog], int]:
        query = select(AuditLog)
        if user_id is not None:
            query = query.where(AuditLog.user_id == user_id)
        if action is not None:
            query = query.where(AuditLog.action == action)
        if resource_type is not None:
            query = query.where(AuditLog.resource_type == resource_type)
        if status is not None:
            query = query.where(AuditLog.status == status)
        if request_id is not None:
            query = query.where(AuditLog.request_id == request_id)
        if created_after is not None:
            query = query.where(AuditLog.created_at >= created_after)
        if created_before is not None:
            query = query.where(AuditLog.created_at <= created_before)

        count_result = await self._session.execute(query.with_only_columns(AuditLog.id))
        total = len(count_result.all())

        result = await self._session.execute(
            query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total
