"""
Prometheus metrics (Phase 9).

Exposes `GET /metrics` in Prometheus's text exposition format — point a
Prometheus server at it (see docker-compose.observability.yml) and the
usual Grafana dashboards / Alertmanager rules work unmodified against
these names.

Deliberately a small, curated set of metrics rather than blanket
auto-instrumentation of every function: each one here answers a specific
operational question a real deploy needs answered (is the app healthy
under load? are OTP emails/SMS actually being delivered? is rate limiting
doing anything?) rather than generating dashboard noise.

**Multi-worker gotcha this module specifically handles:** `prometheus_client`'s
default Counter/Histogram objects live in one process's memory. That's fine
for a single `uvicorn` dev process, but Dockerfile.prod runs `gunicorn` with
multiple worker *processes* — each would keep its own private counters, and
whichever worker happens to handle a given `/metrics` scrape would report
only its own slice of traffic, silently undercounting everything (and the
undercounting would look different on every scrape, since gunicorn round-
robins workers). `prometheus_client` ships an official fix for exactly this
— multiprocess mode, activated by setting `PROMETHEUS_MULTIPROC_DIR` (see
Dockerfile.prod and gunicorn.conf.py) — which this module detects and uses
automatically. Below that env var, nothing changes: single-process `uvicorn`
(dev, or `docker-compose.yml`) keeps using the simple in-memory registry.

Tracing (OpenTelemetry spans) and alerting (Alertmanager rules) are the
other two legs of "full observability" the review asked about. Both are
real follow-up work, not fully wired here: traces need an OTel collector
to send spans to (no such endpoint exists in this sandbox to verify
against), and alerting rules are inherently specific to your on-call
process and SLOs, not something to hardcode into the app. What's here is a
correct, load-bearing foundation for both — every HTTP request already
carries an `X-Request-ID` (see core/middleware.py) that a trace span could
reuse as its trace ID, and every metric below is exactly what a
Prometheus alerting rule would key off of.
"""
import os

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# --- HTTP layer ---
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests processed",
    ["method", "path_template", "status_code"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path_template"],
)

# --- Rate limiting ---
rate_limit_rejections_total = Counter(
    "rate_limit_rejections_total",
    "Requests rejected by the rate limiter",
    ["path_prefix"],
)

# --- Notification delivery (email/SMS) ---
notification_delivery_total = Counter(
    "notification_delivery_total",
    "Notification delivery attempts, by channel and outcome",
    ["channel", "outcome"],  # outcome: "success" | "failure"
)

# --- Banking domain ---
transfers_total = Counter(
    "transfers_total",
    "Money transfers, by outcome",
    ["outcome"],  # "success" | "failed" | "otp_invalid"
)


def render_metrics() -> tuple[bytes, str]:
    """Returns (body, content_type) ready to hand straight to a Response.

    Merges metrics across all gunicorn worker processes when
    PROMETHEUS_MULTIPROC_DIR is set (production); otherwise reads directly
    from this process's in-memory registry (dev/single-process)."""
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import CollectorRegistry, multiprocess

        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST

    return generate_latest(), CONTENT_TYPE_LATEST
