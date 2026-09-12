import re

import httpx
import pytest
import respx
from mergeproof_langfuse import TRACE_URL, LangfuseTraces, LangfuseVerifier

from mergeproof.checks.evidence_links import EvidenceLinks
from mergeproof.context import Context
from mergeproof.report import Status

LINK = "https://lf.example.com/project/p1/traces/t-1"


@respx.mock
def test_verifier_uses_public_api_with_basic_auth(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    route = respx.get("https://lf.example.com/api/public/traces/t-1").mock(return_value=httpx.Response(200, json={}))
    respx.get("https://lf.example.com/api/public/traces/t-2").mock(return_value=httpx.Response(404))
    verifier = LangfuseVerifier()
    assert verifier.verify(LINK, re.match(TRACE_URL, LINK))
    assert not verifier.verify(LINK.replace("t-1", "t-2"), re.match(TRACE_URL, LINK.replace("t-1", "t-2")))
    assert route.calls[0].request.headers["Authorization"].startswith("Basic ")


@respx.mock
def test_host_override_and_server_errors():
    respx.get("https://api.internal/api/public/traces/t-1").mock(return_value=httpx.Response(500))
    verifier = LangfuseVerifier(host="https://api.internal/")
    with pytest.raises(httpx.HTTPStatusError):
        verifier.verify(LINK, re.match(TRACE_URL, LINK))
    with pytest.raises(ValueError):
        LangfuseVerifier().verify("x", re.match(".*", "x"))


def test_langfuse_traces_check_has_defaults_and_stays_an_evidence_links_check():
    check = LangfuseTraces()
    params = check.parse_params({})
    assert params.key == "traces" and params.verify == "langfuse" and params.pattern == TRACE_URL
    assert isinstance(check, EvidenceLinks)
    body = f"```evidence\ntraces:\n  - before: {LINK}\n    after: {LINK.replace('t-1', 't-2')}\n```"
    check.verifier = type("Stub", (), {"verify": lambda self, url, match: match.group("trace_id") == "t-1"})()
    out = check.run(Context(body=body), params, [])
    assert out.status == Status.FAIL and "t-2" in out.details[0]
