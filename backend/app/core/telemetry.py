"""
telemetry.py
============
Configures OpenTelemetry for distributed tracing and custom Prometheus metrics.
"""

import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Histogram

# ── Custom Metrics ────────────────────────────────────────────────────────────
llm_generation_duration = Histogram(
    "llm_generation_duration_seconds",
    "Time spent generating responses from the LLM",
    ["model"],
)


def setup_telemetry(app: FastAPI) -> None:
    """Initialize OpenTelemetry tracing and attach it to the FastAPI app."""

    # Configure Resource identifying the service
    resource = Resource(attributes={SERVICE_NAME: "healthcare-copilot"})

    # Set up Tracer Provider
    provider = TracerProvider(resource=resource)

    # Set up OTLP Exporter (sending to Jaeger OTLP receiver)
    # Default endpoint is localhost:4317 if not specified,
    # but we should use the docker-compose service name if available.
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")

    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    # Register the provider globally
    trace.set_tracer_provider(provider)

    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
