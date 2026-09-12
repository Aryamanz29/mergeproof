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


def test_markdown_comment_reads_like_a_product():
    _, _, report = make_report()
    report.repo, report.base_ref, report.head_sha = "o/r", "main", "abc1234def5678"
    text = render.report_markdown(report, run_url="https://run/1")
    assert text.startswith(render.MARKER)
    assert "**mergeproof**" in text and "img.shields.io/badge/evidence-0%2F2-cf222e" in text
    assert "[policy](https://github.com/o/r/blob/main/mergeproof.yaml)" in text and "[details](https://run/1)" in text
    sentence = "**2 of 2 requirements need attention** for [`abc1234`](https://github.com/o/r/commit/abc1234def5678)"
    assert f"{sentence}: 1 missing, 1 warning." in text
    assert "| Rule | Requirement | Status | Detail |" in text
    assert "| `needs-evidence` | evidence.field | **Missing** |" in text
    assert "|  | pr.labels <sub>warn only</sub> | Warning |" in text
    assert "**Next steps**" in text and "1. **evidence.field**:" in text
    assert "`needs-evidence` <sub>Reproduce on staging.</sub>" in text and "Use the staging tenant." in text
    assert "<details><summary>Evidence template</summary>" in text and "```evidence\nenvironment: staging\n```" in text
    assert "Updated " in text
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
    assert "**All 1 requirements are satisfied**" in text and "Next steps" not in text and "<details>" not in text
    assert "evidence-1%2F1-2ea043" in text
    empty = engine.evaluate(pol, make_context(files=[]), registry)
    empty.rules[0].matched = False
    text = render.report_markdown(empty, marker=False)
    assert text.endswith("No rules apply to this change.") and "evidence-no%20rules" in text


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
    steps = [line for line in text.splitlines() if line[:2] in ("1.", "2.", "3.")]
    assert len(steps) == 3 and "ci.job_passed" not in "".join(steps)
    assert text.count("Do the live thing.") == 1
