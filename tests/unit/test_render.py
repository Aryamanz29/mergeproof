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
    assert "**0 of 2 requirements satisfied, 2 fail**" in text
    assert "| ❌ | evidence.field | `needs-evidence` |" in text
    assert "<sub>warn</sub>" in text
    assert "### What to do" in text and "Use the staging tenant." in text
    assert "Evaluated " in text
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
