"""
Prometheus instrumentation (Monitoring: Prometheus + Grafana, tech-stack §9).

Exposes a /metrics endpoint scraped by kube-prometheus-stack. Besides standard
HTTP RED metrics (Rate/Errors/Duration), we publish ASTRA-specific series the
Grafana dashboard charts: workspace creations, sandbox-tier distribution (B4),
scheduler decisions (B1), and live grid carbon intensity (B6).
"""
from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ── HTTP RED metrics ─────────────────────────────────────────────────────────
HTTP_REQUESTS = Counter(
    "astra_http_requests_total", "HTTP requests",
    ["method", "path", "status"])
HTTP_LATENCY = Histogram(
    "astra_http_request_duration_seconds", "HTTP request latency",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0))

# ── ASTRA domain metrics (referenced by the Grafana dashboard) ───────────────
WORKSPACES_CREATED = Counter(
    "astra_workspaces_created_total", "Workspaces created")
SANDBOX_TIER = Counter(
    "astra_sandbox_tier_total", "Workspaces placed per sandbox tier (B4)",
    ["tier"])
SCHEDULER_DECISIONS = Counter(
    "astra_scheduler_decisions_total", "Scheduler placement decisions (B1)",
    ["algorithm"])
CARBON_INTENSITY = Gauge(
    "astra_carbon_intensity_gco2", "Live grid carbon intensity (B6)",
    ["zone"])
# Queue depth that the KEDA ScaledObject scales the backend on (k8s/base/
# keda-scaledobject.yaml): number of workspaces awaiting placement.
WORKSPACE_PENDING_QUEUE = Gauge(
    "workspace_pending_queue_total", "Workspaces in PENDING state awaiting placement")


def _route(request: Request) -> str:
    """Use the route template (low cardinality) rather than the raw path."""
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            path = _route(request)
            if path != "/metrics":          # don't measure the scrape itself
                HTTP_LATENCY.labels(request.method, path).observe(
                    time.perf_counter() - start)
                HTTP_REQUESTS.labels(request.method, path, str(status)).inc()


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
