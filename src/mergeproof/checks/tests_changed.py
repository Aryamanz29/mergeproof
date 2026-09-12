"""tests.changed - every touched source file must come with a touched test file."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .. import patterns
from ..context import PRContext
from ..models import CheckResult
from .base import Check, failed, passed, skipped


class TestsChanged(Check):
    id = "tests.changed"
    description = (
        "Changed source files must be accompanied by changed (added or modified) test files. "
        "`map` pairs a source glob with `{capture}` segments to a test glob template; "
        "`any_of` alternatively accepts *any* changed file matching those globs."
    )

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")
        map: dict[str, str] = Field(
            default_factory=dict,
            description='e.g. {"src/tools/{name}.py": "tests/**/test_{name}*.py"}',
        )
        any_of: list[str] = Field(
            default_factory=list,
            description="Pass if any changed file matches one of these globs (used when `map` is empty "
            "or as a fallback when `mode` is 'any')",
        )
        mode: str = Field(default="each", pattern="^(each|any)$")
        ignore: list[str] = Field(default_factory=list, description="Source globs exempt from the rule")

    def run(self, ctx: PRContext, params: Params, files: list[str]) -> CheckResult:
        changed = ctx.changed_paths
        if params.mode == "any" or not params.map:
            globs = params.any_of or list(params.map.values())
            hits = [p for p in changed if patterns.any_match(globs, p)]
            if hits:
                return passed(f"{len(hits)} test file(s) changed", details=hits[:10])
            return failed(
                "no test files changed",
                fix="Add or update tests matching: " + ", ".join(globs),
            )

        missing: dict[str, str] = {}
        covered: list[str] = []
        considered = 0
        for src in files:
            if patterns.any_match(params.ignore, src):
                continue
            for src_glob, test_tmpl in params.map.items():
                m = patterns.match(src_glob, src)
                if not m:
                    continue
                considered += 1
                test_glob = patterns.expand(test_tmpl, m.groupdict())
                if any(patterns.match(test_glob, p) for p in changed):
                    covered.append(src)
                else:
                    missing[src] = test_glob
                break
        if considered == 0:
            return skipped("no mapped source files in this change")
        if missing:
            return failed(
                f"{len(missing)} changed source file(s) without test changes",
                details=[f"`{s}` → expected a changed test matching `{g}`" for s, g in missing.items()],
                fix="Add or update the unit tests for each listed file (a regression test that fails "
                "before the fix and passes after it).",
                data={"missing": missing},
            )
        return passed(f"tests changed for all {len(covered)} mapped source file(s)", details=covered[:10])

    def explain(self, params: Params) -> str:
        if params.map and params.mode == "each":
            pairs = "; ".join(f"`{k}` → `{v}`" for k, v in params.map.items())
            return f"Each changed source file needs a changed test file: {pairs}."
        globs = params.any_of or list(params.map.values())
        return "At least one changed test file matching: " + ", ".join(f"`{g}`" for g in globs)
