"""A plugin installed next to mergeproof shows up in `checks` and in `evidence.links` verification."""

from __future__ import annotations

import importlib.util

import pytest

from .conftest import run_cli

pytestmark = pytest.mark.integration

if importlib.util.find_spec("mergeproof_langfuse") is None:
    pytest.skip("install examples/plugins/mergeproof-langfuse to run", allow_module_level=True)


def test_plugin_check_is_discovered():
    proc = run_cli("checks")
    assert proc.returncode == 0 and "langfuse.traces" in proc.stdout


def test_policy_using_plugin_check_validates(tmp_path):
    policy = tmp_path / "mergeproof.yaml"
    policy.write_text("rules:\n  - id: traces\n    require: [{check: langfuse.traces}]\n")
    proc = run_cli("validate", "--policy", str(policy))
    assert proc.returncode == 0, proc.stderr
