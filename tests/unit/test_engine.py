import textwrap

import pytest

from mergeproof import engine, policy, render
from mergeproof.context import Comment
from mergeproof.policy import Severity, When
from mergeproof.report import Report, Status

from .conftest import HEAD, make_context

POLICY = textwrap.dedent("""
    project: demo
    rules:
      - id: tool-tests
        description: tools ship with tests
        when: { paths: ["app/tools/**/*.py"] }
        require:
          - check: tests.changed
            with: { map: { "app/tools/{name}.py": "tests/**/test_{name}*.py" } }
      - id: fix-evidence
        when: { title: "^fix" }
        instructions: Reproduce on staging first.
        require:
          - check: evidence.field
            name: environment
            with: { key: environment, equals: staging }
          - check: evidence.links
            with: { min_pairs: 1 }
          - check: review.human_verified
            name: reviewer verified
          - check: pr.labels
            severity: warn
            with: { any_of: [reviewed] }
      - id: never
        when: { labels: [nope] }
        require: [{ check: pr.body, with: { min_length: 1 } }]
""")

EVIDENCE = "```evidence\nenvironment: staging\nlinks:\n  - before: https://x/1\n    after: https://x/2\n```"


@pytest.fixture
def pol():
    return policy.loads(POLICY)


def test_applies_predicates():
    ctx = make_context(
        files=["a.py", "docs/x.md"], labels=["l1"], title="feat: x", base_ref="release/1", author="bot[bot]"
    )
    assert engine.applies(When(paths=["*.py"]), ctx) == (True, ["a.py"])
    assert engine.applies(When(paths=["*.py"], exclude_paths=["a.py"]), ctx)[0] is False
    assert engine.applies(When(exclude_paths=["docs/**"]), ctx) == (True, ["a.py"])
    assert engine.applies(When(labels=["l1", "zz"]), ctx)[0] is True
    assert engine.applies(When(labels=["zz"]), ctx)[0] is False
    assert engine.applies(When(title="^fix"), ctx)[0] is False
    assert engine.applies(When(base_branches=["release/*"]), ctx)[0] is True
    assert engine.applies(When(authors=["bot[bot]"]), ctx)[0] is True
    assert engine.applies(When(authors=["human"]), ctx)[0] is False
    assert engine.applies(When(), ctx)[0] is True


def test_verdict_progression(pol, registry):
    ctx = make_context(files=["app/tools/lineage.py"])
    report = engine.evaluate(pol, ctx, registry)
    assert [r.id for r in report.matched] == ["tool-tests", "fix-evidence"]
    assert report.verdict == Status.FAIL and report.exit_code == 1
    template = report.evidence_template()
    assert template["environment"] == "staging" and "links" in template

    with_tests = ["app/tools/lineage.py", "tests/test_lineage.py"]
    report = engine.evaluate(pol, make_context(files=with_tests, body=EVIDENCE), registry)
    assert report.verdict == Status.PENDING and report.exit_code == 2

    verified = [Comment(author="lead", body=f"/verified {HEAD[:7]}")]
    ctx = make_context(files=with_tests, body=EVIDENCE, comments=verified)
    report = engine.evaluate(pol, ctx, registry)
    assert report.verdict == Status.WARN and report.exit_code == 0
    assert [req.label for _, req in report.unmet()] == ["pr.labels"]

    ctx = make_context(files=with_tests, body=EVIDENCE, comments=verified, labels=["reviewed"])
    assert engine.evaluate(pol, ctx, registry).verdict == Status.PASS


def test_requirement_severity_overrides_rule(pol, registry):
    ctx = make_context(files=["app/tools/x.py"], title="docs")
    pol.rules[0].severity = Severity.WARN
    assert engine.evaluate(pol, ctx, registry).verdict == Status.WARN


def test_broken_or_unknown_checks_become_errors(pol, registry, monkeypatch):
    from mergeproof.checks import tests_changed

    def boom(self, ctx, params, files):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(tests_changed.TestsChanged, "run", boom)
    report = engine.evaluate(pol, make_context(files=["app/tools/x.py"], title="docs"), registry)
    outcome = report.matched[0].requirements[0].outcome
    assert outcome.status == Status.ERROR and "kaboom" in outcome.summary
    assert report.verdict == Status.FAIL

    pol.rules[0].require[0].check = "made.up"
    report = engine.evaluate(pol, make_context(files=["app/tools/x.py"], title="docs"), registry)
    assert "unknown check" in report.matched[0].requirements[0].outcome.summary
    pol.rules[0].require[0].check = "tests.changed"
    pol.rules[0].require[0].params = {"bogus": 1}
    report = engine.evaluate(pol, make_context(files=["app/tools/x.py"], title="docs"), registry)
    assert "bad parameters" in report.matched[0].requirements[0].outcome.summary


def test_no_rules_apply(pol, registry):
    report = engine.evaluate(pol, make_context(files=["README.md"], title="docs"), registry)
    assert report.verdict == Status.PASS and report.matched == []
    assert "No rules apply" in render.report_markdown(report)
    assert "nothing to check" in render.report_text(report)


def test_headline_counts_and_annotations(pol, registry):
    report = engine.evaluate(pol, make_context(files=["app/tools/lineage.py"]), registry)
    assert report.headline().startswith("0 of 5 requirements satisfied")
    assert "1 pending" in report.headline() and "fail" in report.headline()
    notes = report.annotations()
    assert notes and notes[0].path == "app/tools/lineage.py" and "test_lineage" in notes[0].message
    empty = engine.evaluate(pol, make_context(files=["README.md"], title="docs"), registry)
    assert empty.headline() == "no rules apply to this change"


def test_report_carries_what_the_comment_links_to(pol, registry):
    ctx = make_context(files=["app/tools/x.py"], repo="o/r", number=4, base_ref="release/1")
    report = engine.evaluate(pol, ctx, registry)
    assert (report.repo, report.number, report.base_ref, report.policy_path) == ("o/r", 4, "release/1", "mergeproof.yaml")


def test_report_json_roundtrip(pol, registry):
    report = engine.evaluate(pol, make_context(files=["app/tools/x.py"]), registry)
    again = Report.from_json(report.to_json())
    assert again.verdict == report.verdict and again.rules == report.rules
