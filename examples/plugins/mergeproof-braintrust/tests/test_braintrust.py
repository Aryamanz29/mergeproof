import json
import re

import httpx
import pytest
import respx
from mergeproof_braintrust import TRACE_URL, BraintrustTraces, BraintrustVerifier

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
