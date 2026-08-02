"""
Write-side audit service. Kept intentionally tiny in Phase 1 — any module can
call `write_audit_log` to append an entry. This runs inside the caller's
existing session by default; the Celery-backed async path (background_tasks)
wraps this same function in its own short-lived session so callers on the hot
path are never blocked on audit writes.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit_logs.models import AuditLog


async def write_audit_log(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    action: str,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> None:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        log_metadata=metadata,
    )
    session.add(entry)
    await session.flush()
