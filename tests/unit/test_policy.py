import textwrap

import pytest

from mergeproof import policy

GOOD = textwrap.dedent("""
    rules:
      - id: a
        when: { paths: ["src/**"] }
        require:
          - check: tests.changed
            with: { any_of: ["tests/**"] }
          - check: pr.labels
            name: labelled
            with: { any_of: ["ok"] }
""")


def test_loads_and_defaults():
    pol = policy.loads(GOOD)
    assert pol.version == 1 and pol.evidence_block == "evidence"
    rule = pol.rules[0]
    assert rule.severity == policy.Severity.BLOCK
    assert [r.label for r in rule.require] == ["tests.changed", "labelled"]
    assert policy.When().is_unconditional()


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty policy"),
        ("rules: [", "not valid YAML"),
        ("rules: []", "rules"),
        ("rules:\n  - id: a\n    require: []\n", "require"),
        (
            "rules:\n  - id: a\n    require: [{check: shell}]\n  - id: a\n    require: [{check: shell}]\n",
            "duplicate rule ids",
        ),
        ("rules:\n  - id: a\n    require: [{check: shell}, {check: shell}]\n", "uses 'shell' twice"),
        ("rules:\n  - id: a\n    bogus: 1\n    require: [{check: shell}]\n", "bogus"),
    ],
)
def test_rejects_bad_policies(text, message):
    with pytest.raises(policy.PolicyError) as exc:
        policy.loads(text)
    assert message in str(exc.value)


def test_load_missing_file(tmp_path):
    with pytest.raises(policy.PolicyError, match="not found"):
        policy.load(tmp_path / "nope.yaml")


def test_problems_catch_unknown_checks_and_bad_params(registry):
    pol = policy.loads(GOOD)
    assert policy.problems(pol, registry) == []
    pol.rules[0].require[0].params["nope"] = 1
    pol.rules[0].require[1].check = "made.up"
    found = policy.problems(pol, registry)
    assert len(found) == 2
    assert "nope" in found[0] and "unknown check" in found[1]
