import textwrap

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


def test_markdown_comment_has_marker_table_and_template():
    _, _, report = make_report()
    text = render.report_markdown(report)
    assert text.startswith(render.MARKER)
    assert "`▱▱▱▱▱▱▱▱▱▱` **0 of 2** requirements satisfied · 2 fail" in text
    assert "<details open><summary>❌ <b>needs-evidence</b> · 0 of 2 <sub>prove it</sub></summary>" in text
    assert "| ❌ | evidence.field | " in text and "<sub>warn</sub>" in text
    assert "**To do**" in text and "Use the staging tenant." in text
    assert "📋 Evidence template" in text and "Evaluated " in text
    assert "```evidence\nenvironment: staging\n```" in text
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


def test_satisfied_rules_are_collapsed_and_empty_reports_are_one_line():
    pol = policy.loads("rules:\n  - id: ok\n    require: [{check: pr.labels, with: {none_of: [wip]}}]\n")
    registry = builtin_registry()
    report = engine.evaluate(pol, make_context(files=["a.py"]), registry)
    text = render.report_markdown(report)
    assert "<details><summary>✅ <b>ok</b> · 1 of 1</summary>" in text
    assert "**To do**" not in text and "`▰▰▰▰▰▰▰▰▰▰` **1 of 1**" in text
    assert render.markdown.meter(0, 0) == "" and render.markdown.meter(1, 3) == "`▰▰▰▱▱▱▱▱▱▱`"
    empty = engine.evaluate(pol, make_context(files=[]), registry)
    empty.rules[0].matched = False
    assert render.report_markdown(empty, marker=False) == "✅ **mergeproof**: no rules apply to this change · `abc1234`"
