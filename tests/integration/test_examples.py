"""Every example scenario is run through the real CLI and must produce the verdict it claims."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from .conftest import run_cli, scenarios

pytestmark = pytest.mark.integration

HAS_LANGFUSE_PLUGIN = importlib.util.find_spec("mergeproof_langfuse") is not None
EXIT_FOR = {"pass": 0, "warn": 0, "fail": 1, "pending": 2}


@pytest.mark.parametrize("scenario", list(scenarios()))
def test_scenario_produces_expected_verdict(scenario: Path, tmp_path: Path, langfuse_stub: str):
    data = json.loads(scenario.read_text())
    policy = scenario.parent.parent / "mergeproof.yaml"
    context = json.dumps(data["context"])
    if "{{BASE_URL}}" in context:
        if not HAS_LANGFUSE_PLUGIN:
            pytest.skip("needs the mergeproof-langfuse example plugin installed")
        context = context.replace("{{BASE_URL}}", langfuse_stub)
    context_file = tmp_path / "context.json"
    context_file.write_text(context)

    proc = run_cli("check", "--policy", str(policy), "--context", str(context_file), "--format", "json")
    assert proc.returncode == EXIT_FOR[data["expected"]], proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    verdict = report_verdict(report)
    assert verdict == data["expected"], proc.stdout

    text = run_cli("report", "-", "--format", "md", input=proc.stdout)
    assert text.returncode == 0 and "**mergeproof**" in text.stdout


def report_verdict(report: dict) -> str:
    from mergeproof.report import Report

    return Report.model_validate(report).verdict.value


@pytest.mark.parametrize(
    "policy",
    sorted(Path(__file__).resolve().parents[2].glob("examples/*/mergeproof.yaml")),
    ids=lambda p: p.parent.name,
)
def test_example_policies_validate(policy: Path):
    proc = run_cli("validate", "--policy", str(policy))
    assert proc.returncode == 0, proc.stderr
    prompt = run_cli("agent-prompt", "--policy", str(policy))
    assert prompt.returncode == 0 and "Evidence requirements" in prompt.stdout
