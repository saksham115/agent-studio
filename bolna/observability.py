"""OpenTelemetry tracing → Honeycomb for the Bolna sidecar.

Mirrors backend/app/observability.py: same Honeycomb endpoint, same OTLP
HTTP exporter, no-op when HONEYCOMB_API_KEY is unset. Trace context flows
automatically across the backend → Bolna boundary because httpx and
FastAPI auto-instrumentation use W3C traceparent headers, so spans on
this side stitch into the same trace as the backend's
``orchestrator.process_message``.

Auto-instrumented:
- FastAPI (the /agent REST endpoints — request/response spans)
- httpx (outbound calls to Sarvam STT/TTS, Pellet via OPENAI_BASE_URL)
- redis-py (agent config GET/SET — the per-call lookup at WS open)

Not auto-instrumented (would need Bolna fork or monkey-patch):
- Per-stage transcriber/synthesizer/LLM dispatch inside AssistantManager.
  We add one manual span around AssistantManager.run() to get the per-call
  WS total; finer breakdown requires patching Bolna internals (out of scope
  for this commit — call it out as TODO if needed).
"""

from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_initialised = False


def init_tracing(app=None) -> None:
    """Configure Honeycomb tracing if HONEYCOMB_API_KEY is set."""
    global _initialised
    if _initialised:
        return

    api_key = os.getenv("HONEYCOMB_API_KEY", "")
    if not api_key:
        logger.info("HONEYCOMB_API_KEY unset — Bolna tracing disabled")
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "agent-studio-bolna")

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(
        endpoint="https://api.honeycomb.io/v1/traces",
        headers={"x-honeycomb-team": api_key},
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        except Exception:
            logger.exception("FastAPI auto-instrumentation failed")

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception:
        logger.exception("httpx auto-instrumentation failed")

    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
    except Exception:
        logger.exception("redis auto-instrumentation failed")

    _initialised = True
    logger.info("Honeycomb tracing initialised (service=%s)", service_name)


tracer = trace.get_tracer("agent-studio-bolna")
