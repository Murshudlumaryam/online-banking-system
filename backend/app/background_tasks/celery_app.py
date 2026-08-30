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
    # Bug found during an audit-log verification pass: task_routes alone
    # tells Celery which queue a task *should* go to, but a worker started
    # without an explicit `-Q` flag only ever consumes the single default
    # "celery" queue — it never automatically picks up "audit_queue" or
    # "notification_queue" just because task_routes mentions them. Every
    # write_audit_log_task/send_notification_task dispatched via .delay()
    # was landing in a queue nothing was listening to. task_queues below
    # makes the worker aware of all three queues even when launched with
    # the plain `celery -A ... worker` command (see docker-compose.yml —
    # that invocation is now also fixed to pass -Q explicitly, but this
    # is the actual fix; the -Q flag alone without this would still work,
    # this is what makes it robust to future invocations that forget it).
    task_queues={
        "celery": {"exchange": "celery", "routing_key": "celery"},
        "audit_queue": {"exchange": "audit_queue", "routing_key": "audit_queue"},
        "notification_queue": {"exchange": "notification_queue", "routing_key": "notification_queue"},
        "default_queue": {"exchange": "default_queue", "routing_key": "default_queue"},
    },
    task_default_queue="celery",
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

# Without this, a worker launched as `celery -A app.background_tasks.celery_app
# worker` only ever imports *this* module — none of the @celery_app.task
# decorators in tasks.py execute, so no task is ever registered under this
# worker's app instance, and every .delay() call for it silently sits in
# Redis forever ("Received unregistered task" if a message is ever
# actually delivered to a worker that doesn't have this import). Found the
# same way as the queue-routing bug above: by actually running a worker
# and checking its own startup banner listed zero tasks.
from app.background_tasks import tasks as _tasks  # noqa: E402,F401

# A second, related import-order bug found the same way (running a real
# worker under load, not by reading code): several models declare
# relationships using a *string* class name (e.g. User -> "Customer") to
# avoid circular imports between modules. SQLAlchemy only resolves those
# strings against whatever classes have actually been imported somewhere
# in the process. tasks.py only imports the couple of modules it directly
# needs (audit_logs, mostly) — it never imports customers/accounts/etc. —
# so the very first time this worker process touched the User mapper (via
# write_audit_log_task, unrelated to Customer at all), SQLAlchemy tried to
# resolve "Customer" and failed, because nothing had imported that module
# yet in this process. app.db.models_registry (already used by
# alembic/env.py for the same underlying reason — populating
# Base.metadata) imports every model module for exactly this kind of
# side effect.
from app.db import models_registry as _models_registry  # noqa: E402,F401
