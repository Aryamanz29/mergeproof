import re

import httpx
import pytest
import respx

from mergeproof.verifiers import UnknownVerifier, load_verifier
from mergeproof.verifiers.http import HttpVerifier


@respx.mock
def test_http_verifier_head_then_get_fallback(monkeypatch):
    monkeypatch.setenv("DASH_TOKEN", "secret")
    respx.head("https://dash/ok").mock(
        return_value=httpx.Response(
            200, headers={"content-length": "2048", "content-type": "text/html; charset=utf-8", "last-modified": "Mon"}
        )
    )
    respx.head("https://dash/spa").mock(return_value=httpx.Response(405))
    respx.get("https://dash/spa").mock(return_value=httpx.Response(200))
    respx.head("https://dash/missing").mock(return_value=httpx.Response(404))
    verifier = HttpVerifier(auth_header_env="DASH_TOKEN")
    m = re.match(".*", "")
    ok = verifier.verify("https://dash/ok", m)
    assert ok.found and ok.source == "http" and ok.size == "2,048 bytes" and ok.at == "Mon"
    assert ok.facts == {"status": 200, "type": "text/html"} and ok.url is None
    assert ok.line() == "http · 200 · text/html · 2,048 bytes · Mon"
    assert verifier.verify("https://dash/spa", m).found
    assert not verifier.verify("https://dash/missing", m).found
    sent = respx.calls[0].request.headers["Authorization"]
    assert sent == "Bearer secret"


def test_as_verification_wraps_bools_and_keeps_sources():
    from mergeproof.verifiers import Verification, as_verification

    assert as_verification(True, "stub") == Verification(found=True, source="stub")
    kept = as_verification(Verification(found=True, source="braintrust", size="3 spans"), "stub")
    assert kept.source == "braintrust" and kept.line() == "braintrust · 3 spans"
    assert as_verification(Verification(found=False), "stub").source == "stub"
    assert Verification(found=False).line() == "not found"


def test_load_verifier_builtin_and_unknown():
    assert isinstance(load_verifier("http", {"timeout": 1}), HttpVerifier)
    with pytest.raises(UnknownVerifier):
        load_verifier("nope")
