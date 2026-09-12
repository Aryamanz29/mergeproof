import textwrap

import yaml

from mergeproof.context import Comment
from mergeproof.engine import evaluate, load_policy, match_rule, validate_policy
from mergeproof.models import Match, Policy, Status
from mergeproof.render.markdown import MARKER, render_agent_prompt, render_explain, render_report

from .conftest import FakeContext

POLICY = textwrap.dedent("""
version: 1
project: mcp-server
rules:
  - id: tool-tests
    description: tools ship with tests
    when: { paths: ["mcp/tools/**/*.py"] }
    require:
      - check: tests.changed
        with: { map: { "mcp/tools/{name}.py": "mcp/tests/**/test_{name}*.py" } }
  - id: bugfix-evidence
    when: { title: "^fix" }
    instructions: Reproduce on staging first.
    require:
      - check: evidence.field
        name: tenant
        with: { key: tenant, equals: staging }
      - check: evidence.traces
        with: { project: mcp-internal }
      - check: review.human_verified
        name: reviewer verified
      - check: pr.labels
        severity: warn
        with: { any_of: [reviewed] }
  - id: never
    when: { labels: [nope] }
    require: [{ check: pr.body, with: { min_length: 1 } }]
""")


def policy():
    return Policy.model_validate(yaml.safe_load(POLICY))


def test_validate_policy_reports_bad_config():
    p = policy()
    assert validate_policy(p) == []
    p.rules[0].require[0].params["bogus"] = 1
    assert "bogus" in validate_policy(p)[0]
    p.rules[0].require[0].check = "nope.check"
    assert "unknown check" in validate_policy(p)[0]


def test_load_policy_rejects_duplicates(tmp_path):
    f = tmp_path / "p.yaml"
    rule = "{id: a, require: [{check: shell, with: {run: 'true'}}]}"
    f.write_text(f"rules:\n  - {rule}\n  - {rule}\n")
    try:
        load_policy(str(f))
    except Exception as exc:  # PolicyError
        assert "duplicate rule ids" in str(exc)
    else:
        raise AssertionError("expected PolicyError")


def test_match_rule_predicates():
    ctx = FakeContext(
        files=["a.py", "docs/x.md"], labels=["l1"], title="feat: x", base_ref="release/1", author="bot[bot]"
    )
    assert match_rule(Match(paths=["*.py"]), ctx) == (True, ["a.py"])
    assert match_rule(Match(paths=["*.py"], exclude_paths=["a.py"]), ctx)[0] is False
    assert match_rule(Match(labels=["l1", "zz"]), ctx)[0] is True
    assert match_rule(Match(title="^fix"), ctx)[0] is False
    assert match_rule(Match(base_branches=["release/*"]), ctx)[0] is True
    assert match_rule(Match(authors=["bot[bot]"]), ctx)[0] is True
    assert match_rule(Match(authors=["human"]), ctx)[0] is False
    assert match_rule(Match(), ctx)[0] is True


def test_evaluate_verdicts_and_report():
    ctx = FakeContext(files=["mcp/tools/lineage.py"], body="", labels=[])
    rep = evaluate(policy(), ctx)
    assert [r.rule_id for r in rep.matched_rules] == ["tool-tests", "bugfix-evidence"]
    assert rep.verdict == Status.FAIL
    md = render_report(rep)
    assert MARKER in md and "What is still needed" in md and "```evidence" in md
    tmpl = rep.evidence_template()
    assert tmpl["tenant"] == "staging" and tmpl["traces"][0]["after"].startswith("https://www.braintrust.dev")

    # Provide tests + evidence: only human verification (pending) and the warn-label remain.
    body = (
        "```evidence\ntenant: staging\ntraces:\n  - before: https://www.braintrust.dev/app/o/p/mcp-internal/logs?r=a1\n"
        "    after: https://www.braintrust.dev/app/o/p/mcp-internal/logs?r=b2\n```"
    )
    ctx = FakeContext(files=["mcp/tools/lineage.py", "mcp/tests/unit/test_lineage.py"], body=body)
    rep = evaluate(policy(), ctx)
    assert rep.verdict == Status.PENDING
    ctx = FakeContext(
        files=["mcp/tools/lineage.py", "mcp/tests/unit/test_lineage.py"],
        body=body,
        comments=[Comment("rev", "/verified abc1234")],
    )
    rep = evaluate(policy(), ctx)
    assert rep.verdict == Status.WARN  # only the warn-severity label check is unmet
    ctx.labels = ["reviewed"]
    assert evaluate(policy(), ctx).verdict == Status.PASS


def test_crashing_check_becomes_error(monkeypatch):
    from mergeproof.checks import tests_changed

    def boom(self, ctx, params, files):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(tests_changed.TestsChanged, "run", boom)
    rep = evaluate(policy(), FakeContext(files=["mcp/tools/x.py"]))
    q = rep.matched_rules[0].requirements[0]
    assert q.result.status == Status.ERROR and "kaboom" in q.result.summary
    assert rep.verdict == Status.FAIL


def test_no_rules_matched():
    rep = evaluate(policy(), FakeContext(files=["README.md"], title="docs"))
    assert rep.verdict == Status.PASS and "No rules apply" in render_report(rep)


def test_explain_and_agent_prompt_render():
    p = policy()
    rep = evaluate(p, FakeContext(files=["mcp/tools/lineage.py"], online=False))
    text = render_explain(rep, p)
    assert "## tool-tests" in text and "Evidence block" in text and "only visible in GitHub mode" in text
    prompt = render_agent_prompt(p)
    assert "bugfix-evidence" in prompt and "Never fabricate evidence" in prompt and "tenant: staging" in prompt
