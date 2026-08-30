"""
Regression tests for a critical bug found while verifying the audit log
system end-to-end: `celery_app.py` never imported `tasks.py`, so a worker
launched exactly the way docker-compose.yml launches it
(`celery -A app.background_tasks.celery_app worker`) registered zero
tasks — every `.delay()` call across the entire app (audit logs,
email/SMS notifications) was silently enqueued into a queue nothing
would ever consume, forever. Found by actually running a worker and
reading its own startup banner, not by reading the code.
"""
from app.background_tasks.celery_app import celery_app


def test_all_background_tasks_are_registered_on_the_celery_app():
    registered = {name for name in celery_app.tasks if not name.startswith("celery.")}
    expected = {
        "app.background_tasks.tasks.write_audit_log_task",
        "app.background_tasks.tasks.send_notification_task",
        "app.background_tasks.tasks.expire_stale_transactions_task",
        "app.background_tasks.tasks.execute_scheduled_payments_task",
    }
    missing = expected - registered
    assert not missing, (
        f"these tasks are not registered on celery_app — a worker started with "
        f"`-A app.background_tasks.celery_app` will never execute them: {missing}"
    )


def test_every_routed_task_has_a_queue_the_worker_will_actually_consume():
    """The other half of the same bug: task_routes said "audit_queue" but
    task_queues never declared that queue existed, and the worker command
    in docker-compose.yml had no -Q flag — so even a worker that *did*
    know about the task would only ever listen on the default "celery"
    queue. This checks the routing table's target queues are all
    explicitly declared."""
    routes = celery_app.conf.task_routes or {}
    declared_queues = set(celery_app.conf.task_queues or {})

    for task_name, route in routes.items():
        target_queue = route["queue"]
        assert target_queue in declared_queues, (
            f"{task_name} is routed to {target_queue!r}, which is not in "
            f"task_queues ({declared_queues}) — a worker would never consume it "
            f"unless it also isn't relying on task_queues to know the queue exists"
        )


def test_docker_compose_worker_commands_explicitly_list_every_queue():
    """Belt-and-suspenders check on the actual deployment config, not just
    the Python-side Celery app object — this is what would have caught
    the bug without ever needing to run a real worker."""
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[3]
    for compose_file in ("docker-compose.yml", "docker-compose.prod.yml"):
        path = repo_root / compose_file
        assert path.exists(), f"expected {compose_file} at repo root"
        content = path.read_text()
        # Find the celery worker command line specifically (not the beat one).
        worker_lines = [
            line for line in content.splitlines()
            if "celery" in line and "worker" in line and "command:" in line
        ]
        assert worker_lines, f"no celery worker command found in {compose_file}"
        for line in worker_lines:
            assert "-Q" in line, (
                f"{compose_file}'s celery worker command has no -Q flag, so it will "
                f"only ever consume the default queue: {line.strip()}"
            )
            for queue in ("audit_queue", "notification_queue", "default_queue"):
                assert queue in line, f"{compose_file}'s worker command is missing queue {queue!r}: {line.strip()}"


def test_celery_tasks_use_a_dedicated_unpooled_session_not_the_web_apps_pooled_one():
    """
    Regression test for a second real bug found the same way as the two
    above — by running an actual worker under real load and reading its
    error log, not by inspecting code: every Celery task in tasks.py is a
    plain sync function that calls asyncio.run(...), which creates a
    brand-new event loop on every single invocation. The web app's
    `engine` (app.db.session.engine) is a long-lived, *pooled* engine —
    fine for uvicorn's single persistent event loop, but if a Celery task
    reused it, asyncpg connections established under one asyncio.run()'s
    event loop would get handed back out during a *later* asyncio.run()
    call under a *different* (new) event loop, and asyncpg refuses to use
    a connection outside the loop it was opened on
    ("... attached to a different loop"). This only shows up once the
    pool actually has something to reuse — a single isolated call never
    triggers it, which is why unit tests calling write_audit_log directly
    never caught it.

    The fix is CelerySessionLocal, bound to a NullPool engine so every
    asyncio.run() call gets a genuinely fresh connection with nothing left
    over to misuse later.
    """
    from sqlalchemy.pool import NullPool

    from app.background_tasks import tasks as bg_tasks
    from app.db.session import CelerySessionLocal, celery_engine, engine

    assert bg_tasks.CelerySessionLocal is CelerySessionLocal
    assert isinstance(celery_engine.pool, NullPool)
    # The two engines must be genuinely separate — this is not just "the
    # same pooled engine with a different name".
    assert celery_engine is not engine


def test_celery_worker_process_can_resolve_every_model_relationship():
    """
    Regression test for a third real bug found the same way: tasks.py only
    imports the couple of model modules it directly touches (audit_logs,
    mostly) — it never imports customers/accounts/cards/etc. Several
    models declare relationships using a *string* class name (e.g.
    `User` -> `"Customer"`) specifically to avoid circular imports between
    modules; SQLAlchemy only resolves those strings against whatever
    classes have actually been imported *somewhere* in the current
    process. The first time a real Celery worker process touched the
    `User` mapper (via write_audit_log_task, which has nothing to do with
    Customer at all), configuration failed with "expression 'Customer'
    failed to locate a name" — because nothing in that process had ever
    imported the customers module.

    The fix is importing app.db.models_registry (already used by
    alembic/env.py for the identical underlying reason: populating
    Base.metadata) from celery_app.py, so every model is registered
    before the worker processes its first task.
    """
    from sqlalchemy import inspect

    from app.modules.users.models import User

    # Deliberately does NOT import app.modules.customers.models directly —
    # the whole point is to prove celery_app.py's own import chain is what
    # makes this resolvable, not this test file doing it for it.
    insp = inspect(User)
    assert "customer" in insp.relationships.keys()
    assert "refresh_tokens" in insp.relationships.keys()


