"""Changed source files must come with changed test files."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mergeproof import patterns
from mergeproof.checks.base import Check, fail, ok, plural, skip
from mergeproof.context import Context
from mergeproof.report import Annotation, Outcome


class TestsChanged(Check):
    id = "tests.changed"
    description = "Changed source files are accompanied by added or modified test files."

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        map: dict[str, str] = Field(
            default_factory=dict,
            description="Source glob with {captures} mapped to a test glob, e.g. src/{name}.py to tests/test_{name}.py",
        )
        any_of: list[str] = Field(
            default_factory=list,
            description="Pass when any changed file matches one of these globs; used when `map` is empty",
        )
        ignore: list[str] = Field(default_factory=list, description="Source globs exempt from `map`")
        existing_only: bool = Field(
            default=False,
            description="Only require a test change when a file matching the test glob already exists in the "
            "repository; sources with no test module yet are skipped",
        )

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        changed = ctx.changed_paths
        if not params.map:
            hits = [p for p in changed if patterns.matches_any(params.any_of, p)]
            if hits:
                return ok(f"{plural(len(hits), 'test file')} changed", details=hits[:10])
            return fail("no test files changed", fix="Add or update tests matching " + ", ".join(params.any_of))

        missing: dict[str, str] = {}
        covered: list[str] = []
        without_module: list[str] = []
        for source in files:
            if patterns.matches_any(params.ignore, source):
                continue
            for source_glob, test_template in params.map.items():
                m = patterns.match(source_glob, source)
                if m is None:
                    continue
                test_glob = patterns.expand(test_template, m.groupdict())
                if any(patterns.match(test_glob, p) for p in changed):
                    covered.append(source)
                elif params.existing_only and not self.module_exists(ctx, test_glob):
                    without_module.append(source)
                else:
                    missing[source] = test_glob
                break
        if not missing and not covered:
            if without_module:
                return skip(
                    f"no test module yet for {plural(len(without_module), 'changed file')}", details=without_module[:10]
                )
            return skip("no mapped source files in this change")
        if missing:
            return fail(
                f"{plural(len(missing), 'changed source file')} without test changes",
                details=[f"{src}: expected a changed test matching {glob}" for src, glob in missing.items()],
                fix="Add a regression test for each listed file: it should fail before the change and pass after.",
                data={"missing": missing},
                annotations=[
                    Annotation(path=src, message=f"expected a changed test matching {glob}")
                    for src, glob in missing.items()
                ],
            )
        note = f"; {plural(len(without_module), 'file')} without a test module skipped" if without_module else ""
        return ok(f"tests changed for all {plural(len(covered), 'mapped source file')}{note}", details=covered[:10])

    def module_exists(self, ctx: Context, test_glob: str) -> bool:
        if ctx.tree is None:
            return True  # unknown tree: be strict rather than silently lenient
        return any(patterns.match(test_glob, path) for path in ctx.tree)

    def explain(self, params: Params) -> str:
        if params.map:
            pairs = "; ".join(f"`{src}` needs `{test}`" for src, test in params.map.items())
            tail = " Files whose test module does not exist yet are skipped." if params.existing_only else ""
            return f"Each changed source file needs a changed test file: {pairs}.{tail}"
        return "At least one changed test file matching " + ", ".join(f"`{g}`" for g in params.any_of) + "."
