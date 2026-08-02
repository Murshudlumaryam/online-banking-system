"""
Celery application instance. Queues:
  - audit_queue: high priority, fast (audit trail writes)
  - notification_queue: medium priority (email/SMS dispatch)
  - default_queue: everything else
"""
from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("banking", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "app.background_tasks.tasks.write_audit_log_task": {"queue": "audit_queue"},
        "app.background_tasks.tasks.send_notification_task": {"queue": "notification_queue"},
        "app.background_tasks.tasks.expire_stale_transactions_task": {"queue": "default_queue"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "expire-stale-transactions-every-minute": {
            "task": "app.background_tasks.tasks.expire_stale_transactions_task",
            "schedule": 60.0,
        },
        "execute-scheduled-payments-every-5-minutes": {
            "task": "app.background_tasks.tasks.execute_scheduled_payments_task",
            "schedule": 300.0,
        },
    },
)
