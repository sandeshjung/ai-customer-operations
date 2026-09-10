"""
OpenTelemetry setup for the agent pipeline.

Call `setup_tracing()` once per process (API and worker both do this at
startup) and then use `get_tracer(__name__)` / `traced(...)` anywhere to
add spans. Nested spans automatically parent to whatever span is
"current" on the call stack — no manual context passing needed as long as
everything runs in the same thread (true for our LangGraph nodes and
service functions).

Backend is swappable via env vars alone, no code changes:

- Local Jaeger (default, free, no signup): docker compose already runs
  it — OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318, view traces at
  http://localhost:16686
- Langfuse (self-hosted or cloud): Langfuse ingests OTLP natively as of
  OSS 3.22+. Point OTEL_EXPORTER_OTLP_ENDPOINT at
  https://cloud.langfuse.com/api/public/otel (or your self-hosted URL)
  and set OTEL_EXPORTER_OTLP_HEADERS to a Basic-auth header built from
  your public/secret key — see backend/docs/observability.md.

If the collector is unreachable, the SDK's BatchSpanProcessor swallows
export failures in a background thread — it never raises into request
handling, so a dead Jaeger/Langfuse endpoint degrades to "no traces",
not "broken app".
"""

import base64
import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import settings

logger = logging.getLogger(__name__)

_configured = False

def _parse_headers(raw: str | None) -> dict[str, str]:
    """Parse the standard OTEL_EXPORTER_OTLP_HEADERS format: 'k1=v1,k2=v2'."""
    headers: dict[str, str] = {}
    if not raw:
        return headers
    for pair in raw.split(","):
        if "=" not in pair:
            continue
        key, _, value = pair.partition("=")
        headers[key.strip()] = value.strip()
    return headers

def basic_auth_header(public_key: str, secret_key: str) -> str:
    """Build the 'Authorization=Basic ...' value Langfuse's OTLP endpoint expects."""
    token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    return f"Authorization=Basic {token}"


def setup_tracing(service_name: str | None = None) -> None:
    """Configure the global TracerProvider. Safe to call multiple times."""
    global _configured
    if _configured:
        return

    if not settings.OTEL_ENABLED:
        logger.info("Tracing disabled (OTEL_ENABLED=false)")
        _configured = True
        return

    resource = Resource.create({SERVICE_NAME: service_name or settings.OTEL_SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT.rstrip("/") + "/v1/traces"
    headers = _parse_headers(settings.OTEL_EXPORTER_OTLP_HEADERS)

    exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers or None)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _configured = True

    logger.info("Tracing configured | endpoint=%s | service=%s", endpoint, resource.attributes[SERVICE_NAME])


def get_tracer(name: str):
    return trace.get_tracer(name)


class traced:
    """Context manager wrapping start_as_current_span with error recording.

    Usage:
        with traced("llm.decision", order_id=order_id) as span:
            response = llm.invoke(...)
            span.set_attribute("severity", decision.severity)
    """

    def __init__(self, name: str, tracer_name: str = "app", **attributes):
        self._tracer = get_tracer(tracer_name)
        self._name = name
        self._attributes = {k: v for k, v in attributes.items() if v is not None}
        self._span_cm = None
        self.span = None

    def __enter__(self):
        self._span_cm = self._tracer.start_as_current_span(self._name)
        self.span = self._span_cm.__enter__()
        for key, value in self._attributes.items():
            self.span.set_attribute(key, value)
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            self.span.record_exception(exc_val)
            self.span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc_val)))
        return self._span_cm.__exit__(exc_type, exc_val, exc_tb)


def current_trace_id() -> str | None:
    """Hex trace id of the currently active span, or None if there isn't one."""
    span = trace.get_current_span()
    context = span.get_span_context()
    if not context.is_valid:
        return None
    return format(context.trace_id, "032x")
