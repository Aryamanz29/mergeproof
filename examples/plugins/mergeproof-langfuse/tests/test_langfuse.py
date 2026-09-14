import re

import httpx
import pytest
import respx
from mergeproof_langfuse import TRACE_URL, LangfuseEval, LangfuseTraces, LangfuseVerifier

from mergeproof.checks.evidence_links import EvidenceLinks
from mergeproof.context import Context
from mergeproof.report import Status

LINK = "https://lf.example.com/project/p1/traces/t-1"


@respx.mock
def test_verifier_uses_public_api_with_basic_auth(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    route = respx.get("https://lf.example.com/api/public/traces/t-1").mock(
        return_value=httpx.Response(
            200, json={"name": "search", "timestamp": "2026-09-14T17:02:00Z", "observations": [{}, {}, {}]}
        )
    )
    respx.get("https://lf.example.com/api/public/traces/t-2").mock(return_value=httpx.Response(404))
    verifier = LangfuseVerifier()
    found = verifier.verify(LINK, re.match(TRACE_URL, LINK))
    assert found.found and found.id == "t-1" and found.size == "3 observations" and found.at == "2026-09-14T17:02:00Z"
    assert found.facts == {"project": "p1", "name": "search"}
    assert found.line() == "langfuse · p1 · search · 3 observations · 2026-09-14T17:02:00Z"
    missing = verifier.verify(LINK.replace("t-1", "t-2"), re.match(TRACE_URL, LINK.replace("t-1", "t-2")))
    assert not missing.found and missing.source == "langfuse"
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


def dataset_run_api(host, values):
    items = [{"traceId": f"t-{i}"} for i in range(len(values))]
    respx.get(f"{host}/api/public/datasets/search-golden/runs/pr-7").mock(
        return_value=httpx.Response(
            200, json={"id": "run-1", "name": "pr-7", "createdAt": "2026-09-14T17:00:00Z", "datasetRunItems": items}
        )
    )
    for i, value in enumerate(values):
        scores = [{"name": "correctness", "value": value}, {"name": "note", "value": "n/a"}]
        respx.get(f"{host}/api/public/traces/t-{i}").mock(
            return_value=httpx.Response(200, json={"id": f"t-{i}", "scores": scores})
        )


@respx.mock
def test_eval_averages_trace_scores_over_the_run(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    dataset_run_api("https://lf.example.com", [0.9, 0.8])
    check = LangfuseEval()
    params = check.parse_params({"scorers": {"correctness": 0.8}})
    link = "https://lf.example.com/project/p1/datasets/search-golden/runs/pr-7"
    out = check.run(Context(body=f"```evidence\neval: {link}\n```"), params, [])
    assert out.status == Status.PASS and out.details == [
        "langfuse · pr-7 · 2 examples · 2026-09-14T17:00:00Z",
        "correctness 0.85 ≥ 0.80",
    ]
    assert respx.calls[0].request.headers["Authorization"].startswith("Basic ")

    monkeypatch.setenv("LANGFUSE_HOST", "https://lf.example.com")
    out = check.run(Context(body="```evidence\neval: search-golden/pr-7\n```"), params, [])
    assert out.status == Status.PASS
    monkeypatch.delenv("LANGFUSE_HOST")
    out = check.run(Context(body="```evidence\neval: search-golden/pr-7\n```"), params, [])
    assert out.status == Status.FAIL and "no Langfuse host" in out.summary
    out = check.run(Context(body="```evidence\neval: just-a-name\n```"), params, [])
    assert out.status == Status.FAIL and "<dataset name>/<run name>" in out.summary


@respx.mock
def test_eval_missing_run_and_missing_credentials(monkeypatch):
    check = LangfuseEval()
    params = check.parse_params({"scorers": {"correctness": 0.8}, "host": "https://lf.example.com"})
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    out = check.run(Context(body="```evidence\neval: search-golden/pr-7\n```"), params, [])
    assert out.status == Status.PENDING and "LANGFUSE_PUBLIC_KEY" in out.summary
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    respx.get("https://lf.example.com/api/public/datasets/search-golden/runs/nope").mock(
        return_value=httpx.Response(404)
    )
    out = check.run(Context(body="```evidence\neval: search-golden/nope\n```"), params, [])
    assert out.status == Status.FAIL and "no run 'nope'" in out.summary
