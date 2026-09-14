import json
import re

import httpx
import pytest
import respx
from mergeproof_braintrust import TRACE_URL, BraintrustEval, BraintrustTraces, BraintrustVerifier

from mergeproof.checks.evidence_links import EvidenceLinks
from mergeproof.context import Context
from mergeproof.report import Status

LINK = "https://www.braintrust.dev/app/acme/p/mcp-internal/logs?r=b6f98332e178f658"


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("BRAINTRUST_API_KEY", "k")


def test_pattern_captures_org_project_and_id():
    m = re.match(TRACE_URL, LINK)
    assert m and m.groupdict() == {"org": "acme", "project": "mcp-internal", "trace_id": "b6f98332e178f658"}
    assert re.match(TRACE_URL, "https://www.braintrust.dev/app/acme/p/mcp-internal/logs?s=x&r=abc")


@respx.mock
def test_verifier_queries_btql_by_id_and_root_span():
    rows = [
        {"id": "b6f98332e178f658", "created": "2026-09-14T17:02:01Z", "span_attributes": {"name": "search"}},
        {"id": "child-1", "created": "2026-09-14T17:02:02Z", "span_attributes": {"name": "llm"}},
        {"id": "child-2", "created": "2026-09-14T17:02:03Z", "span_attributes": None},
    ]
    route = respx.post("https://api.braintrust.dev/btql").mock(return_value=httpx.Response(200, json={"data": rows}))
    verifier = BraintrustVerifier()
    found = verifier.verify(LINK, re.match(TRACE_URL, LINK))
    assert found.found and found.size == "3 spans" and found.at == "2026-09-14T17:02:01Z"
    assert found.facts == {"project": "mcp-internal", "name": "search"}
    assert found.line() == "braintrust · mcp-internal · search · 3 spans · 2026-09-14T17:02:01Z"
    sent = json.loads(route.calls[0].request.content)
    assert "project_logs('mcp-internal')" in sent["query"] and "SELECT id, created, span_attributes" in sent["query"]
    assert "id = 'b6f98332e178f658' OR root_span_id = 'b6f98332e178f658'" in sent["query"]
    assert route.calls[0].request.headers["Authorization"] == "Bearer k"


@respx.mock
def test_verifier_reports_missing_and_pins_project():
    route = respx.post("https://api.braintrust.dev/btql").mock(return_value=httpx.Response(200, json={"data": []}))
    verifier = BraintrustVerifier(project="prod")
    missing = verifier.verify(LINK, re.match(TRACE_URL, LINK))
    assert not missing.found and missing.facts == {"project": "prod"}
    assert "project_logs('prod')" in json.loads(route.calls[0].request.content)["query"]


def test_verifier_needs_a_key(monkeypatch):
    monkeypatch.delenv("BRAINTRUST_API_KEY")
    with pytest.raises(ValueError, match="BRAINTRUST_API_KEY"):
        BraintrustVerifier()


def test_check_has_braintrust_defaults():
    check = BraintrustTraces()
    params = check.parse_params({})
    assert (params.key, params.verify, params.pattern) == ("traces", "braintrust", TRACE_URL)
    assert isinstance(check, EvidenceLinks)
    other = LINK.replace("b6f98332e178f658", "db0100b2192984af")
    check.verifier = type("Stub", (), {"verify": lambda self, url, match: match.group("trace_id").startswith("b6")})()
    out = check.run(Context(body=f"```evidence\ntraces:\n  - before: {LINK}\n    after: {other}\n```"), params, [])
    assert out.status == Status.FAIL and "db0100b2192984af" in out.details[0]


EXPERIMENT = "https://www.braintrust.dev/app/acme/p/mcp-internal/experiments/pr-77-search"
EXPERIMENT_ID = "0a1b2c3d-0000-4000-8000-000000000001"


def experiment_api(scores):
    respx.get("https://api.braintrust.dev/v1/experiment").mock(
        return_value=httpx.Response(200, json={"objects": [{"id": EXPERIMENT_ID, "name": "pr-77-search"}]})
    )
    respx.get(f"https://api.braintrust.dev/v1/experiment/{EXPERIMENT_ID}").mock(
        return_value=httpx.Response(
            200, json={"id": EXPERIMENT_ID, "name": "pr-77-search", "created": "2026-09-14T17:00:00Z"}
        )
    )
    return respx.get(f"https://api.braintrust.dev/v1/experiment/{EXPERIMENT_ID}/summarize").mock(
        return_value=httpx.Response(
            200,
            json={
                "experiment_url": EXPERIMENT,
                "scores": {name: {"name": name, "score": value} for name, value in scores.items()},
                "metrics": {"examples": {"name": "examples", "metric": 40}},
            },
        )
    )


@respx.mock
def test_eval_resolves_a_link_by_name_and_reads_the_summary():
    summarize = experiment_api({"Factuality": 0.91, "Safety": 0.99})
    check = BraintrustEval()
    params = check.parse_params({"scorers": {"Factuality": 0.85}})
    out = check.run(Context(body=f"```evidence\neval: {EXPERIMENT}\n```"), params, [])
    assert out.status == Status.PASS and out.summary == "braintrust run scores Factuality 0.91"
    assert out.details == ["braintrust · pr-77-search · 40 examples · 2026-09-14T17:00:00Z", "Factuality 0.91 ≥ 0.85"]
    assert out.data["run"]["url"] == EXPERIMENT and out.data["scores"]["Safety"] == 0.99
    assert summarize.calls[0].request.url.params["summarize_scores"] == "true"
    listing = respx.calls[0].request.url
    assert listing.params["project_name"] == "mcp-internal" and listing.params["experiment_name"] == "pr-77-search"


@respx.mock
def test_eval_accepts_an_id_and_project_slash_name_and_fails_below_the_bar():
    experiment_api({"Factuality": 0.7})
    check = BraintrustEval()
    params = check.parse_params({"scorers": {"Factuality": 0.85}})
    out = check.run(Context(body=f"```evidence\neval: {EXPERIMENT_ID}\n```"), params, [])
    assert out.status == Status.FAIL and "Factuality 0.70 is below 0.85" in out.summary
    out = check.run(Context(body="```evidence\neval: mcp-internal/pr-77-search\n```"), params, [])
    assert out.status == Status.FAIL and out.details[1] == "Factuality 0.70 < 0.85"
    out = check.run(Context(body="```evidence\neval: pr-77-search\n```"), params, [])
    assert out.status == Status.FAIL and "<project>/<name>" in out.summary


def test_eval_is_pending_without_a_key(monkeypatch):
    monkeypatch.delenv("BRAINTRUST_API_KEY")
    check = BraintrustEval()
    out = check.run(
        Context(body=f"```evidence\neval: {EXPERIMENT}\n```"), check.parse_params({"scorers": {"F": 1}}), []
    )
    assert out.status == Status.PENDING and "BRAINTRUST_API_KEY" in out.summary
