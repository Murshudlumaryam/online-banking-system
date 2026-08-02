"""
Gunicorn config (production only — see Dockerfile.prod).

The only thing this file does beyond gunicorn's CLI flags is the
`child_exit` hook, which wires in prometheus_client's multiprocess cleanup:
when a worker process exits (graceful restart, crash, `--max-requests`
recycling, etc.), `mark_process_dead` removes that worker's *Gauge* metric
files — a Gauge represents "current" state (e.g. in-flight requests), and a
dead worker's last-known value would otherwise linger and skew readings.

This app doesn't define any Gauge metrics today (only Counter/Histogram —
see app/core/metrics.py), so this hook is currently a no-op in practice.
It's kept in place anyway as the correct, standard wiring for whenever a
Gauge is added later (e.g. "active DB connections"), since forgetting it at
that point would be a subtle, easy-to-miss bug.

Counter/Histogram files are deliberately NOT touched here — verified this
manually (kill -TERM a worker mid-load-test, confirm /metrics still shows
the dead worker's pre-exit request count correctly summed into the total,
not reset to 0). Prometheus counters are cumulative; deleting a dead
worker's file would make the total silently go backwards, which is worse
than leaving a small number of harmless historical files around.
"""


def child_exit(server, worker):
    import os

    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)
