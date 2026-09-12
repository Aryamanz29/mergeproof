"""shell - run a repo-provided command; exit 0 passes.

The command comes from the *policy file*, never from PR content. Changed paths and PR metadata are
exposed through environment variables (not interpolated into the command line).
"""

from __future__ import annotations

import os
import subprocess

from pydantic import BaseModel, ConfigDict, Field

from ..context import PRContext
from ..models import CheckResult
from .base import Check, errored, failed, passed


class Shell(Check):
    id = "shell"
    description = (
        "Run a command from the policy; exit code 0 passes. "
        "Env: MERGEPROOF_FILES, MERGEPROOF_HEAD_SHA, MERGEPROOF_BASE_REF."
    )

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")
        run: str
        cwd: str = "."
        timeout: int = 600
        env: dict[str, str] = Field(default_factory=dict)
        tail: int = Field(default=20, description="Lines of output to include in the report")

    def run(self, ctx: PRContext, params: Params, files: list[str]) -> CheckResult:
        env = {
            **os.environ,
            **params.env,
            "MERGEPROOF_FILES": "\n".join(files),
            "MERGEPROOF_HEAD_SHA": ctx.head_sha or "",
            "MERGEPROOF_BASE_REF": ctx.base_ref,
        }
        try:
            proc = subprocess.run(
                params.run,
                shell=True,
                cwd=os.path.join(ctx.root, params.cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=params.timeout,
            )
        except subprocess.TimeoutExpired:
            return errored(f"`{params.run}` timed out after {params.timeout}s")
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-params.tail :]
        if proc.returncode == 0:
            return passed(f"`{params.run}` exit 0", details=tail)
        return failed(
            f"`{params.run}` exit {proc.returncode}",
            details=tail,
            fix="Run the command locally and fix what it reports.",
        )

    def explain(self, params: Params) -> str:
        return f"`{params.run}` exits 0."
