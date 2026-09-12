"""A named check run on the head commit succeeded.

A commit can carry several check runs with the same name: re-runs, and runs a
concurrency group cancelled when a newer push arrived. Only the newest run per
name says anything about the commit, so that is the one that counts.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from mergeproof.checks.base import Check, fail, ok, pending, plural
from mergeproof.context import CheckRun, Context
from mergeproof.report import Outcome


def newest_per_name(runs: list[CheckRun]) -> list[CheckRun]:
    latest: dict[str, CheckRun] = {}
    for run in runs:
        current = latest.get(run.name)
        if current is None or run.started_at > current.started_at:
            latest[run.name] = run
    return list(latest.values())


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
        runs = newest_per_name(runs)
        if not runs:
            message = (
                f"no check run matching `{params.name}` yet"
                if params.regex
                else f"no check run named `{params.name}` yet"
            )
            return fail(message) if params.missing == "fail" else pending(message)
        failed = [r for r in runs if r.status == "completed" and r.conclusion not in ("success", "skipped", "neutral")]
        running = [r for r in runs if r.status != "completed"]
        succeeded = [r for r in runs if r.status == "completed" and r.conclusion == "success"]
        if failed:
            return fail(
                f"{plural(len(failed), 'run')} failed",
                details=[f"{r.name}: {r.conclusion}" + (f" {r.url}" if r.url else "") for r in failed],
                fix="Make the job green; the gate re-evaluates on the next run.",
            )
        if running:
            return pending(f"{plural(len(running), 'run')} still in progress", details=[r.name for r in running])
        if len(succeeded) < params.min_matches:
            return fail(f"{plural(len(succeeded), 'successful run')}, need {params.min_matches}")
        return ok(f"{plural(len(succeeded), 'run')} succeeded", details=[r.name for r in succeeded][:10])

    def explain(self, params: Params) -> str:
        how = "matching" if params.regex else "named"
        return f"CI check run {how} `{params.name}` is green on the head commit."
