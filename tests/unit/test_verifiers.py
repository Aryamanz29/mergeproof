import re

import httpx
import pytest
import respx

from mergeproof.verifiers import UnknownVerifier, load_verifier
from mergeproof.verifiers.http import HttpVerifier


@respx.mock
def test_http_verifier_head_then_get_fallback(monkeypatch):
    monkeypatch.setenv("DASH_TOKEN", "secret")
    respx.head("https://dash/ok").mock(return_value=httpx.Response(200))
    respx.head("https://dash/spa").mock(return_value=httpx.Response(405))
    respx.get("https://dash/spa").mock(return_value=httpx.Response(200))
    respx.head("https://dash/missing").mock(return_value=httpx.Response(404))
    verifier = HttpVerifier(auth_header_env="DASH_TOKEN")
    m = re.match(".*", "")
    assert verifier.verify("https://dash/ok", m)
    assert verifier.verify("https://dash/spa", m)
    assert not verifier.verify("https://dash/missing", m)
    sent = respx.calls[0].request.headers["Authorization"]
    assert sent == "Bearer secret"


def test_load_verifier_builtin_and_unknown():
    assert isinstance(load_verifier("http", {"timeout": 1}), HttpVerifier)
    with pytest.raises(UnknownVerifier):
        load_verifier("nope")
