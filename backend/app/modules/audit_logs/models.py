"""
Minimal audit_logs model for Phase 1 (login/register events only).
Admin-facing read/search endpoints are implemented in Phase 4.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Append-only audit trail. No updated_at/soft-delete — rows are immutable."""

    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # SUCCESS / FAILED. Nullable rather than a hard enum column — older
    # rows written before this field existed have no value, and some
    # actions (e.g. a pure informational event) genuinely have no
    # pass/fail outcome to record. New call sites should always set it
    # where the action has one (see app/modules/audit_logs/actions.py's
    # AuditStatus).
    status: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    log_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
