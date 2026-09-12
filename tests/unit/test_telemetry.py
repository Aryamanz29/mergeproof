import sys

import pytest

from mergeproof import telemetry


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in (*telemetry.ENDPOINT_VARS, "OTEL_SDK_DISABLED", "OTEL_SERVICE_NAME"):
        monkeypatch.delenv(var, raising=False)


def test_nothing_happens_without_an_endpoint():
    assert telemetry.wanted() is False
    assert telemetry.configure() is False


def test_disabled_flag_wins(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    assert telemetry.configure() is False


def test_missing_exporter_is_reported_not_fatal(monkeypatch, capsys):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", None)
    assert telemetry.configure() is False
    assert "mergeproof[otel]" in capsys.readouterr().err


def test_configure_installs_a_provider_with_service_metadata(monkeypatch):
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://127.0.0.1:1/v1/traces")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "mergeproof-test")
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", None, raising=False)
    monkeypatch.setattr(trace, "_TRACER_PROVIDER_SET_ONCE", trace.Once(), raising=False)
    assert telemetry.configure() is True
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)
    assert provider.resource.attributes["service.name"] == "mergeproof-test"
    assert provider.resource.attributes["service.version"] == telemetry.__version__
    provider.shutdown()
