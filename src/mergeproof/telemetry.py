"""OpenTelemetry export for the MCP server.

The MCP SDK already wraps every request in a span. Those spans go nowhere until a tracer
provider with an exporter is installed, which is what :func:`configure` does when the
standard ``OTEL_EXPORTER_OTLP_ENDPOINT`` variable is set. Without it, nothing changes and
nothing is imported.
"""

from __future__ import annotations

import os
import sys

from mergeproof import __version__

ENDPOINT_VARS = ("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT")


def wanted() -> bool:
    if os.environ.get("OTEL_SDK_DISABLED", "").lower() == "true":
        return False
    return any(os.environ.get(var) for var in ENDPOINT_VARS)


def configure(service_name: str = "mergeproof") -> bool:
    """Install an OTLP/HTTP exporter if the environment asks for one. Returns whether it did."""
    if not wanted():
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        print(
            "mergeproof: OTEL_EXPORTER_OTLP_ENDPOINT is set but the exporter is not installed; "
            "pip install 'mergeproof[otel]'",
            file=sys.stderr,
        )
        return False
    resource = Resource.create(
        {SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", service_name), SERVICE_VERSION: __version__}
    )
    provider = TracerProvider(resource=resource, shutdown_on_exit=True)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    return True
