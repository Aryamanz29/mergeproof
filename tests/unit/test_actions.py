import textwrap

from mergeproof import engine, policy, render
from mergeproof.checks.registry import builtin_registry

from .conftest import make_context

POLICY = textwrap.dedent("""
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
    report = engine.evaluate(policy.loads(POLICY), make_context(files=["src/a:b.py"], online=False), builtin_registry())
    lines = render.workflow_commands(report)
    assert lines[0].startswith(
        "::error file=src/a%3Ab.py,line=1,title=mergeproof%3A tests.changed::expected a changed test"
    )
    assert lines[1].startswith("::warning file=src/a%3Ab.py,line=1,title=mergeproof%3A docs tests::")
    assert lines[-1] == "::error title=mergeproof::0 of 2 requirements satisfied, 2 fail"


def test_nothing_is_emitted_when_everything_passes():
    report = engine.evaluate(policy.loads(POLICY), make_context(files=["README.md"], online=False), builtin_registry())
    assert render.workflow_commands(report) == []
