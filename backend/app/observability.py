"""OpenTelemetry tracing → Honeycomb.

Initialised once at FastAPI startup. No-op when HONEYCOMB_API_KEY is unset
(local dev / non-prod deploys without a key configured stay silent — no
exporter background threads, no per-span overhead).

Wires three things:

1. **OTLP HTTP exporter** to ``https://api.honeycomb.io/v1/traces`` with
   the Honeycomb API key in the ``x-honeycomb-team`` header.
2. **Auto-instrumentation** for FastAPI (request spans), httpx (outbound
   calls to Pellet / Bolna become spans), and SQLAlchemy (each query a
   span). Together these give the bulk of the waterfall for free.
3. A module-level ``tracer`` for **manual spans** at boundaries the
   auto-instrumenters can't see — e.g. orchestrator stages (KB retrieval,
   guardrails, tool loop) which run inside a single FastAPI request.
"""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings

logger = logging.getLogger(__name__)

_initialised = False


def init_tracing(app=None) -> None:
    """Set up Honeycomb tracing if HONEYCOMB_API_KEY is configured.

    Call once during FastAPI startup. Passing the FastAPI ``app`` enables
    request-level instrumentation (per-route spans with method / status).
    """
    global _initialised
    if _initialised:
        return
    if not settings.HONEYCOMB_API_KEY:
        logger.info("HONEYCOMB_API_KEY unset — tracing disabled")
        return

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )

    resource = Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(
        endpoint="https://api.honeycomb.io/v1/traces",
        headers={"x-honeycomb-team": settings.HONEYCOMB_API_KEY},
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI / httpx / SQLAlchemy. Each is best-effort:
    # if the package isn't importable we skip it rather than fail startup.
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
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()
    except Exception:
        logger.exception("SQLAlchemy auto-instrumentation failed")

    _initialised = True
    logger.info(
        "Honeycomb tracing initialised (service=%s)", settings.OTEL_SERVICE_NAME
    )


# Module-level tracer for manual spans. Safe to import even when tracing
# is disabled — the no-op tracer provider returns no-op spans.
tracer = trace.get_tracer("agent-studio")
