import json
import textwrap
from xml.etree import ElementTree as ET

from mergeproof import engine, policy, render
from mergeproof.checks.registry import builtin_registry
from mergeproof.cli import explanations
from mergeproof.report import Status

from .conftest import make_context

POLICY = textwrap.dedent("""
    rules:
      - id: needs-evidence
        description: prove it
        when: { paths: ["src/**"], authors: ["bot[bot]"] }
        instructions: Reproduce on staging.
        require:
          - check: evidence.field
            with: { key: environment, equals: staging }
            instructions: Use the staging tenant.
          - check: pr.labels
            severity: warn
            with: { any_of: [ok] }
""")


def make_report():
    pol = policy.loads(POLICY)
    registry = builtin_registry()
    ctx = make_context(files=["src/a.py"], author="bot[bot]", online=False)
    return pol, registry, engine.evaluate(pol, ctx, registry)


def test_markdown_comment_is_a_scorecard():
    _, _, report = make_report()
    report.repo, report.base_ref, report.head_sha = "o/r", "main", "abc1234def5678"
    text = render.report_markdown(report, run_url="https://run/1")
    assert text.startswith(render.MARKER)
    first = text.splitlines()[1]
    assert first.startswith("![mergeproof: 0 / 2](https://img.shields.io/badge/mergeproof-0%20%2F%202-cf222e")
    assert "logo=data:image/svg+xml;base64," in first
    assert "![needs evidence: 0 / 2](https://img.shields.io/badge/needs%20evidence-0%20%2F%202-cf222e" in first
    assert (
        "**0 of 2 requirements satisfied** for [`abc1234`](https://github.com/o/r/commit/abc1234def5678). To merge:"
        in text
    )
    assert "| Needed | What to do |" in text
    assert (
        "| ![Missing](https://img.shields.io/badge/Missing-cf222e" in text
        and "evidence.field<br><sub>needs-evidence</sub> |" in text
    )
    assert "<sub>**needs-evidence**: Reproduce on staging.</sub>" in text
    assert (
        "**Evidence template**, to paste into the PR description:" in text
        and "```evidence\nenvironment: staging\n```" in text
    )
    assert "**Everything else**" in text and "| ![Warning](https://img.shields.io/badge/Warning-dbab09" in text
    assert "<details>" not in text
    assert "[policy](https://github.com/o/r/blob/main/mergeproof.yaml)" in text and "[details](https://run/1)" in text
    for icon in render.markdown.ICON.values():
        assert icon not in text
    assert render.MARKER not in render.report_markdown(report, marker=False)


def test_text_report_is_compact_and_actionable():
    _, _, report = make_report()
    text = render.report_text(report)
    assert text.splitlines()[0].startswith("mergeproof: FAIL")
    assert "FAIL  evidence.field:" in text and "fix:" in text
    assert "evidence block to add" in text
    verbose = render.report_text(report, verbose=True)
    assert len(verbose) >= len(text)


def test_explain_markdown_lists_requirements_with_explanations():
    pol, registry, report = make_report()
    text = render.explain_markdown(report, pol, explanations(pol, registry))
    assert text.startswith("# What this change must prove (fail)")
    assert "## needs-evidence [block]" in text
    assert "Triggered by `src/a.py`." in text
    assert "`environment` present and equal to `staging`." in text
    assert "note: Use the staging tenant." in text


def test_agent_prompt_mirrors_the_policy():
    pol, registry, _ = make_report()
    text = render.agent_prompt(pol, registry)
    assert "### `needs-evidence`: prove it" in text
    assert "authored by `bot[bot]`" in text and "files matching `src/**`" in text
    assert "Never fabricate evidence" in text
    assert "```evidence\nenvironment: staging\n```" in text


def test_icons_cover_every_status():
    assert set(render.markdown.ICON) == set(Status)
    assert set(render.text.TAG) == set(Status)


def test_all_satisfied_and_no_rules_variants():
    pol = policy.loads("rules:\n  - id: ok\n    require: [{check: pr.labels, with: {none_of: [wip]}}]\n")
    registry = builtin_registry()
    report = engine.evaluate(pol, make_context(files=["a.py"]), registry)
    text = render.report_markdown(report)
    assert "**All 1 requirements satisfied**" in text and "To merge" not in text
    assert "![ok: 1 / 1](https://img.shields.io/badge/ok-1%20%2F%201-2ea043" in text
    assert "| ![Satisfied](https://img.shields.io/badge/Satisfied-2ea043" in text
    empty = engine.evaluate(pol, make_context(files=[]), registry)
    empty.rules[0].matched = False
    text = render.report_markdown(empty, marker=False)
    assert "No rules apply to this change." in text and "no%20rules%20apply" in text


def test_next_steps_skip_unactionable_pending_and_state_rule_instructions_once():
    from mergeproof.context import CheckRun

    text_policy = textwrap.dedent("""
        rules:
          - id: live
            instructions: Do the live thing.
            require:
              - check: ci.job_passed
                with: { name: unit }
              - check: review.human_verified
              - check: evidence.field
                with: { key: a }
              - check: evidence.field
                name: b
                with: { key: b }
    """)
    pol = policy.loads(text_policy)
    report = engine.evaluate(
        pol, make_context(files=["x"], check_runs=[CheckRun(name="unit", status="in_progress")]), builtin_registry()
    )
    text = render.report_markdown(report)
    needed = text.split("| Needed | What to do |", 1)[1].split("**Everything else**", 1)[0]
    steps = [line for line in needed.splitlines() if line.startswith("| ![")]
    assert len(steps) == 3 and "ci.job_passed" not in "".join(steps)
    assert text.count("Do the live thing.") == 1


FORMATS_POLICY = textwrap.dedent("""
    rules:
      - id: tests
        when: { paths: ["src/**"] }
        require:
          - check: tests.changed
            with: { map: { "src/{name}.py": "tests/test_{name}.py" } }
          - check: ci.job_passed
            with: { name: unit }
      - id: labels
        severity: warn
        require:
          - check: pr.labels
            with: { any_of: [ok] }
""")


def formats_report():
    pol = policy.loads(FORMATS_POLICY)
    return engine.evaluate(pol, make_context(files=["src/a.py", "src/b.py"], labels=["ok"]), builtin_registry())


def test_junit_maps_rules_to_suites_and_requirements_to_cases():
    doc = ET.fromstring(render.junit_xml(formats_report()))
    assert doc.tag == "testsuites" and doc.get("tests") == "3"
    assert doc.get("failures") == "1" and doc.get("skipped") == "1"
    suites = {s.get("name"): s for s in doc.findall("testsuite")}
    assert set(suites) == {"tests", "labels"}
    cases = {c.get("name"): c for c in suites["tests"].findall("testcase")}
    failure = cases["tests.changed"].find("failure")
    assert failure is not None and "without test changes" in failure.get("message")
    assert "src/a.py" in failure.text and "fix:" in failure.text
    assert cases["ci.job_passed"].find("skipped").get("message").startswith("pending:")
    assert suites["labels"].find("testcase").find("failure") is None


def test_rdjson_carries_file_annotations():
    data = json.loads(render.rdjson(formats_report()))
    assert data["source"]["name"] == "mergeproof" and data["severity"] == "ERROR"
    paths = sorted(d["location"]["path"] for d in data["diagnostics"])
    assert paths == ["src/a.py", "src/b.py"]
    first = data["diagnostics"][0]
    assert first["severity"] == "ERROR" and first["code"]["value"] == "tests"
    assert first["location"]["range"]["start"]["line"] == 1
    assert first["message"].startswith("tests.changed: expected a changed test matching")


ACTIONS_POLICY = textwrap.dedent("""
    rules:
      - id: tests
        when: { paths: ["src/**"] }
        require:
          - check: tests.changed
            with: { map: { "src/{name}.py": "tests/test_{name}.py" } }
      - id: soft
        severity: warn
        when: { paths: ["src/**"] }
        require:
          - check: tests.changed
            name: docs tests
            with: { map: { "src/{name}.py": "docs/{name}.md" } }
""")


def test_workflow_commands_annotate_files_and_state_the_verdict():
    report = engine.evaluate(
        policy.loads(ACTIONS_POLICY), make_context(files=["src/a:b.py"], online=False), builtin_registry()
    )
    lines = render.workflow_commands(report)
    assert lines[0].startswith(
        "::error file=src/a%3Ab.py,line=1,title=mergeproof%3A tests.changed::expected a changed test"
    )
    assert lines[1].startswith("::warning file=src/a%3Ab.py,line=1,title=mergeproof%3A docs tests::")
    assert lines[-1] == "::error title=mergeproof::0 of 2 requirements satisfied, 1 missing, 1 warning"


def test_nothing_is_emitted_when_everything_passes():
    report = engine.evaluate(
        policy.loads(ACTIONS_POLICY), make_context(files=["README.md"], online=False), builtin_registry()
    )
    assert render.workflow_commands(report) == []


def test_footer_links_the_receipt_when_there_is_one():
    pol = policy.loads(
        textwrap.dedent(
            """
            rules:
              - id: r
                when: { paths: ["src/**"] }
                require:
                  - check: files.changed
                    with: { any_of: ["src/**"] }
            """
        )
    )
    report = engine.evaluate(pol, make_context(files=["src/a.py"], repo="o/r", base_ref="main"), builtin_registry())
    text = render.report_markdown(report, run_url="https://run/1", receipt_url="https://github.com/o/r/blob/x/r.json")
    assert "[details](https://run/1) · [receipt](https://github.com/o/r/blob/x/r.json)" in text
    assert "[receipt]" not in render.report_markdown(report, run_url="https://run/1")


def test_satisfied_rows_show_what_was_found():
    from mergeproof.report import Outcome, Report, RequirementResult, RuleResult

    req = RequirementResult(
        label="before/after traces",
        check="evidence.links",
        severity="block",
        outcome=Outcome(
            status=Status.PASS,
            summary="1 before/after pair, all verified",
            details=["before: braintrust · 3 spans", "after: braintrust · 14 spans | more"],
        ),
    )
    rule = RuleResult(id="live-evidence", severity="block", matched=True, files=["src/a.py"], requirements=[req])
    text = render.report_markdown(Report(rules=[rule]))
    detail = "before: braintrust · 3 spans<br>after: braintrust · 14 spans \\| more"
    assert f"1 before/after pair, all verified<br><sub>{detail}</sub>" in text
