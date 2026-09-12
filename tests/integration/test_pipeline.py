"""The plumbing commands compose with a shell pipe, the way the README promises."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_context_check_report_pipeline(sample_repo: Path):
    cli = f"{shlex.quote(sys.executable)} -m mergeproof"
    pipeline = (
        f"{cli} context --local --base main"
        f" | {cli} check --context - --format json"
        f" | {cli} report - --format md --exit-status"
    )
    proc = subprocess.run(["sh", "-c", pipeline], cwd=sample_repo, capture_output=True, text=True)
    assert proc.returncode == 1, proc.stderr
    assert "evidence missing" in proc.stdout and "```evidence" in proc.stdout


def test_template_then_check_passes(sample_repo: Path):
    cli = [sys.executable, "-m", "mergeproof"]
    template = subprocess.run(
        [*cli, "template", "--local", "--base", "main"], cwd=sample_repo, capture_output=True, text=True
    )
    assert template.returncode == 0 and "environment: staging" in template.stdout
    (sample_repo / "body.md").write_text("## Summary\n\n" + template.stdout)
    (sample_repo / "tests").mkdir()
    (sample_repo / "tests" / "test_app.py").write_text("def test_value():\n    pass\n")
    check = subprocess.run(
        [*cli, "check", "--local", "--base", "main", "--body-file", "body.md"],
        cwd=sample_repo,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    assert check.stdout.startswith("mergeproof: PASS")


def test_step_summary_and_output_are_written(sample_repo: Path, tmp_path: Path):
    env = os.environ | {"GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"), "GITHUB_OUTPUT": str(tmp_path / "out.txt")}
    proc = subprocess.run(
        [sys.executable, "-m", "mergeproof", "check", "--local", "--base", "main", "-q"],
        cwd=sample_repo,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 1 and proc.stdout == ""
    assert "<!-- mergeproof-report -->" in (tmp_path / "summary.md").read_text()
    assert (tmp_path / "out.txt").read_text() == "verdict=fail\n"
