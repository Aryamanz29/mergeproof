"""A named check run on the head commit succeeded."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from mergeproof.checks.base import Check, fail, ok, pending
from mergeproof.context import Context
from mergeproof.report import Outcome


class CiJobPassed(Check):
    id = "ci.job_passed"
    description = "A GitHub check run on the head commit completed successfully."
    needs_github = True

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        name: str = Field(description="Check run name, or a regex when `regex` is true")
        regex: bool = False
        min_matches: int = Field(default=1, description="How many matching runs must succeed")
        missing: str = Field(default="pending", pattern="^(pending|fail)$", description="Status when no run exists yet")

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        if not ctx.online:
            return pending(f"CI status for `{params.name}` is only visible in GitHub mode")
        if params.regex:
            wanted = re.compile(params.name)
            runs = [r for r in ctx.check_runs if wanted.search(r.name)]
        else:
            runs = [r for r in ctx.check_runs if r.name == params.name]
        if not runs:
            message = f"no check run named `{params.name}` on {ctx.head_short or 'the head commit'}"
            return fail(message) if params.missing == "fail" else pending(message)
        failed = [r for r in runs if r.status == "completed" and r.conclusion not in ("success", "skipped", "neutral")]
        running = [r for r in runs if r.status != "completed"]
        succeeded = [r for r in runs if r.status == "completed" and r.conclusion == "success"]
        if failed:
            return fail(
                f"{len(failed)} run(s) failed",
                details=[f"{r.name}: {r.conclusion}" + (f" {r.url}" if r.url else "") for r in failed],
                fix="Make the job green; the gate re-evaluates on the next run.",
            )
        if running:
            return pending(f"{len(running)} run(s) still in progress", details=[r.name for r in running])
        if len(succeeded) < params.min_matches:
            return fail(f"{len(succeeded)} successful run(s), need {params.min_matches}")
        return ok(f"{len(succeeded)} run(s) succeeded", details=[r.name for r in succeeded][:10])

    def explain(self, params: Params) -> str:
        how = "matching" if params.regex else "named"
        return f"CI check run {how} `{params.name}` is green on the head commit."
