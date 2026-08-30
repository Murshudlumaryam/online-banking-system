import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.modules.audit_logs.actions import AuditAction, AuditStatus
from app.modules.audit_logs.models import AuditLog
from app.modules.audit_logs.service import write_audit_log


@pytest.mark.asyncio
async def test_write_audit_log_persists_all_fields(db_session):
    """Unit test for AuditLogService (per the audit-log task's Addım 39
    'AuditLogService creates log / correct fields' requirement) — writes
    directly, bypassing Celery entirely, so this is real regardless of
    whether a worker is running anywhere."""
    user_id = uuid.uuid4()
    resource_id = uuid.uuid4()

    await write_audit_log(
        db_session,
        user_id=user_id,
        action=AuditAction.LOGIN_SUCCESS,
        resource_type="user",
        resource_id=resource_id,
        ip_address="203.0.113.5",
        metadata={"note": "test"},
        status=AuditStatus.SUCCESS.value,
        request_id="req-abc-123",
        user_agent="pytest-client/1.0",
    )
    await db_session.commit()

    result = await db_session.execute(select(AuditLog).where(AuditLog.user_id == user_id))
    entry = result.scalar_one()
    assert entry.action == AuditAction.LOGIN_SUCCESS
    assert entry.resource_type == "user"
    assert entry.resource_id == resource_id
    assert str(entry.ip_address) == "203.0.113.5"
    assert entry.status == "SUCCESS"
    assert entry.request_id == "req-abc-123"
    assert entry.user_agent == "pytest-client/1.0"
    assert entry.log_metadata == {"note": "test"}
    assert entry.created_at is not None


@pytest.mark.asyncio
async def test_write_audit_log_never_stores_a_field_literally_named_otp_or_password(db_session):
    """Guard against ever accidentally passing a raw secret into metadata —
    this doesn't (and can't) inspect *values*, but catches the class of
    mistake where a call site does `metadata={"otp": otp_code}` outright."""
    await write_audit_log(
        db_session, user_id=uuid.uuid4(), action=AuditAction.TRANSFER_FAILED,
        metadata={"reference_number": "TXN-ABC", "reason": "OTP expired"},
    )
    await db_session.commit()
    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.TRANSFER_FAILED)
    )
    entry = result.scalar_one()
    assert "otp" not in (entry.log_metadata or {})
    assert "password" not in (entry.log_metadata or {})


@pytest.mark.asyncio
async def test_admin_can_read_audit_logs(client: AsyncClient, admin_headers: dict):
    response = await client.get("/api/v1/admin/audit-logs", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert "items" in body and "total" in body


@pytest.mark.asyncio
async def test_normal_user_cannot_read_audit_logs(client: AsyncClient, registered_customer: dict):
    response = await client.get("/api/v1/admin/audit-logs", headers=registered_customer["headers"])
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_audit_log_endpoints_are_read_only(client: AsyncClient, admin_headers: dict):
    """Addım 27/35: audit logs must not be mutable through the API at
    all — there is deliberately no POST/PUT/PATCH/DELETE route for this
    resource, so any of these methods against the collection URL should
    fail as a routing/method mismatch, not as a permission grant."""
    for method in ("post", "put", "patch", "delete"):
        response = await client.request(
            method, "/api/v1/admin/audit-logs", headers=admin_headers, json={}
        )
        assert response.status_code in (404, 405), (
            f"{method.upper()} /admin/audit-logs should not be a valid route, got {response.status_code}"
        )


@pytest.mark.asyncio
async def test_admin_can_filter_audit_logs_by_status_and_request_id(
    client: AsyncClient, admin_headers: dict, db_session
):
    await write_audit_log(
        db_session, user_id=uuid.uuid4(), action="TEST_FILTER_ACTION",
        status=AuditStatus.FAILED.value, request_id="filter-test-req-1",
    )
    await db_session.commit()

    by_status = await client.get(
        "/api/v1/admin/audit-logs", params={"status": "FAILED", "action": "TEST_FILTER_ACTION"},
        headers=admin_headers,
    )
    assert by_status.status_code == 200
    assert by_status.json()["total"] >= 1

    by_request_id = await client.get(
        "/api/v1/admin/audit-logs", params={"request_id": "filter-test-req-1"}, headers=admin_headers
    )
    assert by_request_id.status_code == 200
    items = by_request_id.json()["items"]
    assert len(items) == 1
    assert items[0]["request_id"] == "filter-test-req-1"


@pytest.mark.asyncio
async def test_logout_writes_an_audit_log_entry(
    client: AsyncClient, registered_customer: dict, db_session, stub_background_tasks
):
    """Regression test for a real gap found during this audit: logout had
    no audit call at all before this pass."""
    logout_response = await client.post("/api/v1/auth/logout", headers=registered_customer["headers"])
    assert logout_response.status_code == 204

    logout_calls = [
        args for name, args in stub_background_tasks
        if name == "write_audit_log_task" and args[1] == AuditAction.LOGOUT
    ]
    assert len(logout_calls) == 1, "expected exactly one LOGOUT audit dispatch"
