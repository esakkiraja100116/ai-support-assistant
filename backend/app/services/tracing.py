"""OpenTelemetry tracing: exports one trace per chat turn (root span
"chat_turn", created in orchestrator.chat_turn()/StreamedChatTurn) to Grafana
Cloud via OTLP, with a child span around each meaningful step - intent
routing, each tool's lookup+judgment call, and the final answer-generation
call - so a single trace shows the whole turn end-to-end: user query -> tool
result -> final LLM call.

A BatchSpanProcessor batches and exports spans in the background after each
span ends, not as a continuous stream - this is periodic observability
export, not live log tailing.

No-ops safely (OTel's default no-op TracerProvider stays in place) when
OTEL_EXPORTER_OTLP_ENDPOINT isn't configured, so local dev without a Grafana
Cloud account and the test suite are both unaffected - `tracer` is always
safe to import and use, real provider or not.
"""
import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings

logger = logging.getLogger(__name__)

# get_tracer() returns a proxy that binds to whatever TracerProvider is
# active when a span is actually created, not at this call - safe to create
# here at import time, before init_tracing() has necessarily run yet.
tracer = trace.get_tracer("ai-support-assistant")

_initialized = False


def _parse_headers(raw: str) -> dict[str, str]:
    """Supports the documented OTEL_EXPORTER_OTLP_HEADERS format
    (key1=value1,key2=value2). If no `=` is present at all, treats the whole
    value as a bare Grafana Cloud OTLP auth token and wraps it as
    `Authorization: Basic <token>`, since that's what Grafana's own setup
    wizard produces when its copy-paste output is trimmed to just the
    header value."""
    raw = raw.strip()
    if not raw:
        return {}
    if "=" not in raw:
        return {"Authorization": f"Basic {raw}"}
    headers: dict[str, str] = {}
    for pair in raw.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            headers[key.strip()] = value.strip()
    return headers


def init_tracing() -> None:
    global _initialized
    if _initialized or not settings.otel_exporter_otlp_endpoint:
        return

    resource = Resource.create(
        {
            "service.name": "ai-support-assistant-backend",
            "deployment.environment": settings.environment,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=f"{settings.otel_exporter_otlp_endpoint.rstrip('/')}/v1/traces",
        headers=_parse_headers(settings.otel_exporter_otlp_headers),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _initialized = True
    logger.info("OpenTelemetry tracing initialized (environment=%s)", settings.environment)
