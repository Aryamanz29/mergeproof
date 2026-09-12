"""ci.job_passed - a named GitHub check run on the head commit must have succeeded."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from ..context import PRContext
from ..models import CheckResult
from .base import Check, failed, passed, pending


class CiJobPassed(Check):
    id = "ci.job_passed"
    description = "A GitHub check run (CI job) on the head commit must have completed successfully."
    needs_github = True

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str = Field(description="Check-run name; a regex when `regex: true`")
        regex: bool = False
        min_matches: int = Field(default=1, description="How many matching runs must succeed")
        missing: str = Field(
            default="pending", pattern="^(pending|fail)$", description="Status when no run with that name exists yet"
        )

    def run(self, ctx: PRContext, params: Params, files: list[str]) -> CheckResult:
        if not ctx.online:
            return pending(f"CI status for `{params.name}` is only visible in GitHub mode")
        rx = re.compile(params.name) if params.regex else None
        runs = [r for r in ctx.check_runs() if (rx.search(r.name) if rx else r.name == params.name)]
        if not runs:
            msg = f"no check run named `{params.name}` on {ctx.head_short}"
            return failed(msg) if params.missing == "fail" else pending(msg)
        running = [r for r in runs if r.status != "completed"]
        bad = [r for r in runs if r.status == "completed" and r.conclusion not in ("success", "skipped", "neutral")]
        good = [r for r in runs if r.status == "completed" and r.conclusion == "success"]
        if bad:
            return failed(
                f"{len(bad)} run(s) failed",
                details=[f"{r.name}: {r.conclusion} {r.url or ''}" for r in bad],
                fix="Make the job green; the gate re-evaluates automatically.",
            )
        if running:
            return pending(f"{len(running)} run(s) still in progress", details=[r.name for r in running])
        if len(good) < params.min_matches:
            return failed(f"{len(good)} successful run(s), need {params.min_matches}")
        return passed(f"{len(good)} run(s) succeeded", details=[r.name for r in good][:10])

    def explain(self, params: Params) -> str:
        kind = "matching" if params.regex else "named"
        return f"CI check run {kind} `{params.name}` green on the head commit."
