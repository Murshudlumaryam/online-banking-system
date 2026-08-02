"""
Celery tasks. Each task opens its own short-lived async DB session — never
share a session between the request/response cycle and a background task.
"""
import asyncio
import logging
import uuid

from app.background_tasks.celery_app import celery_app
from app.db.session import AsyncSessionLocal
from app.modules.audit_logs.service import write_audit_log

logger = logging.getLogger("app.background_tasks")


async def _write_audit_log_async(
    user_id: str | None,
    action: str,
    resource_type: str | None,
    resource_id: str | None,
    ip_address: str | None,
    metadata: dict | None,
) -> None:
    async with AsyncSessionLocal() as session:
        await write_audit_log(
            session,
            user_id=uuid.UUID(user_id) if user_id else None,
            action=action,
            resource_type=resource_type,
            resource_id=uuid.UUID(resource_id) if resource_id else None,
            ip_address=ip_address,
            metadata=metadata,
        )
        await session.commit()


@celery_app.task(name="app.background_tasks.tasks.write_audit_log_task", max_retries=3)
def write_audit_log_task(
    user_id: str | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> None:
    asyncio.run(
        _write_audit_log_async(user_id, action, resource_type, resource_id, ip_address, metadata)
    )


_EMAIL_TEMPLATES: dict[str, tuple[str, str]] = {
    "transfer_otp": (
        "Your transfer confirmation code",
        "Your one-time code to confirm transfer {reference_number} is: {otp_code}\n\n"
        "This code expires shortly. If you didn't request this transfer, "
        "please contact support immediately and consider changing your password.",
    ),
    "transfer_completed": (
        "Transfer completed",
        "Your transfer {reference_number} has completed successfully.",
    ),
    "password_reset": (
        "Reset your password",
        "We received a request to reset your password. Use this token in the "
        "app to set a new password (it expires in 15 minutes):\n\n{reset_token}\n\n"
        "If you didn't request this, you can safely ignore this email.",
    ),
    "account_status_changed": (
        "Your account status has changed",
        "Your account status is now: {status}",
    ),
}

# SMS templates are single short strings (no subject line) — carriers often
# truncate or bill per ~160-char segment, so these stay terse.
_SMS_TEMPLATES: dict[str, str] = {
    "transfer_otp": "Your confirmation code is {otp_code}. It expires shortly. Never share this code.",
    "transfer_completed": "Your transfer {reference_number} has completed successfully.",
    "password_reset": "A password reset was requested for your account. If this wasn't you, contact support.",
    "account_status_changed": "Your account status is now: {status}",
}


def _render_template(body_template: str, context: dict) -> str:
    try:
        return body_template.format(**context)
    except KeyError:
        # Unknown/missing template placeholder — degrade gracefully rather
        # than losing the notification entirely.
        return f"{body_template}\n\n(context: {context})"


async def _send_notification_async(user_id: str, channel: str, template: str, context: dict) -> None:
    import uuid as uuid_module

    async with AsyncSessionLocal() as session:
        from app.modules.users.repository import UserRepository

        user = await UserRepository(session).get_by_id(uuid_module.UUID(user_id))
        if user is None:
            logger.warning("notification_recipient_not_found", extra={"user_id": user_id})
            return

        if channel == "email":
            from app.core.email import create_email_provider

            subject, body_template = _EMAIL_TEMPLATES.get(template, (template, "{context}"))
            body = _render_template(body_template, context)
            email_provider = create_email_provider()
            await email_provider.send(to_address=user.email, subject=subject, body=body)

        elif channel == "sms":
            from app.core.sms import create_sms_provider
            from app.modules.customers.repository import CustomerRepository

            customer = await CustomerRepository(session).get_by_user_id(user.id)
            if customer is None:
                logger.warning("sms_recipient_has_no_customer_profile", extra={"user_id": user_id})
                return

            body_template = _SMS_TEMPLATES.get(template, template)
            body = _render_template(body_template, context)
            sms_provider = create_sms_provider()
            await sms_provider.send(to_number=customer.phone_number, body=body)

        else:
            logger.info(
                "notification_dispatched_unknown_channel",
                extra={"user_id": user_id, "channel": channel, "template": template},
            )


@celery_app.task(name="app.background_tasks.tasks.send_notification_task", max_retries=3)
def send_notification_task(user_id: str, channel: str, template: str, context: dict) -> None:
    asyncio.run(_send_notification_async(user_id, channel, template, context))


async def _expire_stale_transactions_async() -> int:
    """
    Sweeps PENDING transactions whose OTP challenge has expired and were
    never confirmed by the customer, marking them FAILED. This is a
    housekeeping safety net — the confirm endpoint already rejects an
    expired OTP on-demand, but a transaction the customer simply abandons
    (never calls /confirm again) would otherwise stay PENDING forever.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.modules.transactions.models import (
        Transaction,
        TransactionStatus,
        TransferConfirmation,
    )
    from app.modules.transactions.repository import TransactionRepository

    expired_count = 0
    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(Transaction, TransferConfirmation)
            .join(TransferConfirmation, TransferConfirmation.transaction_id == Transaction.id)
            .where(
                Transaction.status == TransactionStatus.PENDING,
                TransferConfirmation.expires_at <= now,
            )
        )
        transactions_repo = TransactionRepository(session)
        for transaction, _confirmation in result.all():
            await transactions_repo.mark_failed(transaction, "OTP expired (auto-expired by housekeeping sweep)")
            expired_count += 1
        await session.commit()
    return expired_count


@celery_app.task(name="app.background_tasks.tasks.expire_stale_transactions_task")
def expire_stale_transactions_task() -> int:
    return asyncio.run(_expire_stale_transactions_async())


async def _execute_scheduled_payments_async() -> dict:
    """
    Executes every due, active scheduled payment. Each schedule is
    processed independently — one failing (e.g. insufficient balance)
    never blocks the others. Failures are recorded on the schedule itself
    (last_failure_reason) rather than raised, since this runs unattended on
    a fixed interval with no one to receive an exception.
    """
    from app.core.exceptions import DomainError
    from app.modules.customers.repository import CustomerRepository
    from app.modules.scheduled_payments.repository import ScheduledPaymentRepository
    from app.modules.transactions.service import TransactionService

    executed, failed = 0, 0
    async with AsyncSessionLocal() as session:
        schedules_repo = ScheduledPaymentRepository(session)
        customers_repo = CustomerRepository(session)
        transaction_service = TransactionService(session)

        due_schedules = await schedules_repo.list_due()
        for schedule in due_schedules:
            customer = await customers_repo.get_by_id(schedule.customer_id)
            if customer is None:
                await schedules_repo.record_failure(schedule, "Customer no longer exists")
                await session.commit()
                failed += 1
                continue
            try:
                transaction = await transaction_service.execute_scheduled_transfer(
                    customer,
                    sender_account_id=schedule.sender_account_id,
                    receiver_account_number=schedule.receiver_account_number,
                    amount=schedule.amount,
                    currency=schedule.currency,
                )
                await schedules_repo.record_success(schedule, transaction.id)
                await session.commit()
                executed += 1
            except DomainError as exc:
                # execute_scheduled_transfer's inner locked-execution step
                # already rolled back and marked the transaction FAILED
                # (and committed) before re-raising — the session is
                # already clean here, so there's nothing left to roll back.
                await schedules_repo.record_failure(schedule, str(exc))
                await session.commit()
                failed += 1

    return {"executed": executed, "failed": failed}


@celery_app.task(name="app.background_tasks.tasks.execute_scheduled_payments_task")
def execute_scheduled_payments_task() -> dict:
    return asyncio.run(_execute_scheduled_payments_async())
