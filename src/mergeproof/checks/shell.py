"""Run a command from the policy; exit status 0 passes.

The command text comes from the policy file, never from the pull request.
Changed paths and commit information reach it through environment variables.
"""

from __future__ import annotations

import os
import subprocess

from pydantic import BaseModel, ConfigDict, Field

from mergeproof.checks.base import Check, error, fail, ok, skip
from mergeproof.context import Context
from mergeproof.report import Outcome


class Shell(Check):
    id = "shell"
    description = (
        "A command from the policy exits 0. MERGEPROOF_FILES, MERGEPROOF_HEAD_SHA and MERGEPROOF_BASE_REF are set."
    )

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        run: str
        cwd: str = "."
        timeout: int = 600
        env: dict[str, str] = Field(default_factory=dict)
        tail: int = Field(default=20, description="Trailing output lines kept in the report")

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        if not ctx.has_checkout:
            return skip("needs a checkout; not available when mergeproof runs as a GitHub App")
        env = os.environ | params.env
        env["MERGEPROOF_FILES"] = "\n".join(files)
        env["MERGEPROOF_HEAD_SHA"] = ctx.head_sha or ""
        env["MERGEPROOF_BASE_REF"] = ctx.base_ref
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
            return error(f"`{params.run}` timed out after {params.timeout}s")
        output = (proc.stdout + proc.stderr).strip().splitlines()[-params.tail :]
        if proc.returncode == 0:
            return ok(f"`{params.run}` exited 0", details=output)
        return fail(
            f"`{params.run}` exited {proc.returncode}",
            details=output,
            fix="Run the command locally and fix what it reports.",
        )

    def explain(self, params: Params) -> str:
        return f"`{params.run}` exits 0."
