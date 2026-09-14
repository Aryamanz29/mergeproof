"""The public surface is a promise. Changing this list is a review conversation."""

import importlib
from pathlib import Path

import pytest

import mergeproof
from mergeproof import policy
from mergeproof.checks.registry import load_registry

ROOT = Path(__file__).resolve().parents[2]

PUBLIC = {
    "Annotation",
    "ChangedFile",
    "Check",
    "CheckRun",
    "Comment",
    "Context",
    "EvalRun",
    "EvalScore",
    "MissingCredentials",
    "Outcome",
    "Policy",
    "PolicyError",
    "Report",
    "Requirement",
    "RequirementResult",
    "Rule",
    "RuleResult",
    "Severity",
    "Status",
    "Verification",
    "Verifier",
    "When",
    "__version__",
    "error",
    "fail",
    "ok",
    "pending",
    "skip",
    "warn",
}


def test_the_public_names_are_exactly_these():
    assert set(mergeproof.__all__) == PUBLIC
    for name in PUBLIC:
        assert getattr(mergeproof, name) is not None


def test_check_and_verifier_signatures_are_stable():
    import inspect

    assert list(inspect.signature(mergeproof.Check.run).parameters) == ["self", "ctx", "params", "files"]
    assert list(inspect.signature(mergeproof.Check.explain).parameters) == ["self", "params"]
    assert list(inspect.signature(mergeproof.Check.evidence_template).parameters) == ["self", "params"]
    assert list(inspect.signature(mergeproof.Verifier.verify).parameters) == ["self", "url", "match"]
    assert list(inspect.signature(mergeproof.EvalScore.fetch_run).parameters) == ["self", "ref", "match", "params"]


@pytest.mark.parametrize("path", sorted(ROOT.glob("examples/*/mergeproof.yaml")), ids=lambda p: p.parent.name)
def test_every_example_policy_loads_against_the_current_schema(path):
    pol = policy.load(path)
    assert pol.version == 1 and pol.rules
    registry = load_registry()
    unknown = {req.check for rule in pol.rules for req in rule.require if registry.lookup(req.check) is None}
    plugin_checks = {c for c in unknown if c.split(".")[0] in ("langfuse", "braintrust")}
    assert unknown == plugin_checks, f"unknown built-in checks: {unknown - plugin_checks}"
    if plugin_checks:
        pytest.importorskip("mergeproof_" + next(iter(plugin_checks)).split(".")[0])
        assert not policy.problems(pol, load_registry())


@pytest.mark.parametrize("module", ["mergeproof_langfuse", "mergeproof_braintrust"])
def test_example_plugins_build_only_on_public_names(module):
    plugin = pytest.importorskip(module)
    source = Path(plugin.__file__).read_text()
    for line in source.splitlines():
        if line.startswith("from mergeproof"):
            head = line.split(" import ")[0]
            assert head in (
                "from mergeproof",
                "from mergeproof.checks.eval_score",
                "from mergeproof.checks.evidence_links",
                "from mergeproof.verifiers",
            ), line
    eval_check = next(n for n in dir(plugin) if n.endswith("Eval"))
    assert issubclass(getattr(plugin, eval_check), mergeproof.EvalScore)
    importlib.import_module(module)
