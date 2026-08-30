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
