import httpx
import pytest

from mergeproof.checks.ci_job import CiJobPassed
from mergeproof.checks.evidence_field import EvidenceField
from mergeproof.checks.human_verified import HumanVerified
from mergeproof.checks.tests_changed import TestsChanged
from mergeproof.checks.traces import EvidenceTraces
from mergeproof.context import CheckRun, Comment
from mergeproof.models import Status

from .conftest import FakeContext


def run(check, ctx, files=None, **params):
    p = check.parse_params(params)
    return check.run(ctx, p, files if files is not None else ctx.changed_paths)


# tests.changed -------------------------------------------------------------------------

MAP = {"modelcontextprotocol/tools/{name}.py": "modelcontextprotocol/tests/unit/**/test_{name}*.py"}


def test_tests_changed_each_missing():
    ctx = FakeContext(
        files=[
            "modelcontextprotocol/tools/lineage.py",
            "modelcontextprotocol/tools/query.py",
            "modelcontextprotocol/tests/unit/test_query.py",
        ]
    )
    r = run(TestsChanged(), ctx, map=MAP)
    assert r.status == Status.FAIL
    assert "lineage" in r.details[0] and len(r.data["missing"]) == 1


def test_tests_changed_each_ok_and_skip():
    ctx = FakeContext(
        files=["modelcontextprotocol/tools/lineage.py", "modelcontextprotocol/tests/unit/tools/test_lineage_batch.py"]
    )
    assert run(TestsChanged(), ctx, map=MAP).status == Status.PASS
    ctx = FakeContext(files=["README.md"])
    assert run(TestsChanged(), ctx, map=MAP).status == Status.SKIP


def test_tests_changed_any_mode():
    ctx = FakeContext(files=["src/a.py"])
    assert run(TestsChanged(), ctx, any_of=["tests/**"]).status == Status.FAIL
    ctx = FakeContext(files=["src/a.py", "tests/test_a.py"])
    assert run(TestsChanged(), ctx, any_of=["tests/**"]).status == Status.PASS


# evidence.field ------------------------------------------------------------------------


def test_evidence_field():
    ctx = FakeContext(body="```evidence\ntenant: staging\nimage: ghcr.io/x/y:pr-1\n```")
    assert run(EvidenceField(), ctx, key="tenant", equals="staging").status == Status.PASS
    assert run(EvidenceField(), ctx, key="tenant", equals="prod").status == Status.FAIL
    assert run(EvidenceField(), ctx, key="image", matches=r":pr-\d+$").status == Status.PASS
    r = run(EvidenceField(), ctx, key="missing")
    assert r.status == Status.FAIL and "missing" in r.summary
    assert run(EvidenceField(), FakeContext(body=""), key="tenant").status == Status.FAIL


def test_evidence_field_template_nested():
    p = EvidenceField().parse_params({"key": "image.tag", "example": "pr-123"})
    assert EvidenceField().evidence_template(p) == {"image": {"tag": "pr-123"}}


# evidence.traces -----------------------------------------------------------------------


def body_with(pairs, project="mcp-internal"):
    base = f"https://www.braintrust.dev/app/acme/p/{project}/logs?r="
    items = "\n".join(f"  - tool: t\n    before: {base}{b}\n    after: {base}{a}" for b, a in pairs)
    return f"```evidence\ntraces:\n{items}\n```"


def test_traces_pairs():
    ctx = FakeContext(body=body_with([("aaa1", "bbb2")]))
    r = run(EvidenceTraces(), ctx, project="mcp-internal")
    assert r.status == Status.PASS and r.data["pairs"][0]["after"] == "bbb2"


def test_traces_reject_same_wrong_project_and_missing():
    assert run(EvidenceTraces(), FakeContext(body=body_with([("aaa1", "aaa1")]))).status == Status.FAIL
    r = run(EvidenceTraces(), FakeContext(body=body_with([("a1", "b2")], project="other")), project="mcp-internal")
    assert r.status == Status.FAIL and "project" in r.details[0]
    assert run(EvidenceTraces(), FakeContext(body="")).status == Status.FAIL
    r = run(EvidenceTraces(), FakeContext(body=body_with([("a1", "b2")])), min_pairs=2)
    assert r.status == Status.FAIL and "need 2" in r.summary


class StubVerifier:
    def __init__(self, known):
        self.known = set(known)

    def exists(self, project, trace_id):
        return trace_id in self.known


def test_traces_verify_uses_verifier():
    ctx = FakeContext(body=body_with([("aaa1", "bbb2")]))
    chk = EvidenceTraces()
    chk.verifier = StubVerifier({"aaa1", "bbb2"})
    assert run(chk, ctx, verify=True).status == Status.PASS
    chk.verifier = StubVerifier({"aaa1"})
    r = run(chk, ctx, verify=True)
    assert r.status == Status.FAIL and "bbb2" in r.details[0]


def test_traces_verify_without_key_is_error(monkeypatch):
    monkeypatch.delenv("BRAINTRUST_API_KEY", raising=False)
    r = run(EvidenceTraces(), FakeContext(body=body_with([("a1", "b2")])), verify=True)
    assert r.status == Status.ERROR


def test_braintrust_verifier_query(monkeypatch):
    from mergeproof.checks.traces import BraintrustVerifier

    captured = {}

    def handler(request: httpx.Request):
        captured["json"] = request.read().decode()
        return httpx.Response(200, json={"data": [{"id": "abc"}]})

    v = BraintrustVerifier("k")
    v._client = httpx.Client(base_url="https://api.braintrust.dev", transport=httpx.MockTransport(handler))
    assert v.exists("mcp-internal", "abc'; drop") is True
    assert "project_logs('mcp-internal')" in captured["json"] and "drop" not in captured["json"]


# ci.job_passed -------------------------------------------------------------------------


def test_ci_job():
    runs = [
        CheckRun("🧪 Integration Tests · lineage", "completed", "success"),
        CheckRun("🧪 Integration Tests · query", "in_progress", None),
        CheckRun("lint", "completed", "failure"),
    ]
    ctx = FakeContext(check_runs=runs)
    assert run(CiJobPassed(), ctx, name="lint").status == Status.FAIL
    assert run(CiJobPassed(), ctx, name="Integration Tests", regex=True).status == Status.PENDING
    assert run(CiJobPassed(), ctx, name=r"Integration Tests · lineage", regex=True).status == Status.PASS
    assert run(CiJobPassed(), ctx, name="nope").status == Status.PENDING
    assert run(CiJobPassed(), ctx, name="nope", missing="fail").status == Status.FAIL
    assert run(CiJobPassed(), FakeContext(online=False), name="lint").status == Status.PENDING


# review.human_verified -----------------------------------------------------------------


def test_human_verified_rules():
    hv = HumanVerified()
    author_self = Comment("octocat", "/verified abc1234")
    bot = Comment("claude[bot]", "/verified abc1234")
    stale = Comment("reviewer", "/verified 0000000")
    good = Comment("reviewer", "looked at both traces, /verified abc1234", url="u")

    r = run(hv, FakeContext(comments=[author_self, bot, stale]))
    assert r.status == Status.PENDING and len(r.details) == 3
    r = run(hv, FakeContext(comments=[good]))
    assert r.status == Status.PASS and r.data["by"] == "reviewer"
    assert run(hv, FakeContext(comments=[stale]), bind_to_head=False).status == Status.PASS
    assert run(hv, FakeContext(comments=[good]), allowed_users=["someone-else"]).status == Status.PENDING
    rev = Comment("reviewer", "/verified abc1234", kind="review", state="COMMENTED")
    assert run(hv, FakeContext(comments=[rev]), require_review_state="APPROVED").status == Status.PENDING


@pytest.mark.parametrize("check", [HumanVerified(), CiJobPassed()])
def test_needs_github_flag(check):
    assert check.needs_github


# agent.verdict -------------------------------------------------------------------------


def verdict_comment(author, head="abc1234", verdict="pass", conf=0.9, at="2026-01-01T00:00:00Z", name="trace-review"):
    body = (
        f"<!-- v -->\n```verdict\ncheck: {name}\nverdict: {verdict}\nhead: {head}\nconfidence: {conf}\nsummary: ok\n```"
    )
    return Comment(author, body, created_at=at)


def test_agent_verdict():
    from mergeproof.checks.agent_verdict import AgentVerdict

    av = AgentVerdict()
    bot = "github-actions[bot]"
    assert run(av, FakeContext(comments=[]), name="trace-review").status == Status.PENDING
    assert (
        run(av, FakeContext(comments=[verdict_comment(bot)]), name="trace-review", authors=[bot]).status == Status.PASS
    )
    r = run(av, FakeContext(comments=[verdict_comment("rando")]), name="trace-review", authors=[bot])
    assert r.status == Status.PENDING and "not an allowed" in r.details[0]
    assert (
        run(av, FakeContext(comments=[verdict_comment(bot, head="0000000")]), name="trace-review").status
        == Status.PENDING
    )
    assert (
        run(av, FakeContext(comments=[verdict_comment(bot, verdict="fail")]), name="trace-review").status == Status.FAIL
    )
    assert (
        run(av, FakeContext(comments=[verdict_comment(bot, conf=0.5)]), name="trace-review", min_confidence=0.8).status
        == Status.PENDING
    )
    # latest verdict wins
    cs = [
        verdict_comment(bot, verdict="fail", at="2026-01-01T00:00:00Z"),
        verdict_comment(bot, verdict="pass", at="2026-01-02T00:00:00Z"),
    ]
    assert run(av, FakeContext(comments=cs), name="trace-review").status == Status.PASS
    # other check names are ignored
    assert (
        run(av, FakeContext(comments=[verdict_comment(bot, name="other")]), name="trace-review").status
        == Status.PENDING
    )
    assert run(av, FakeContext(online=False), name="trace-review").status == Status.PENDING
