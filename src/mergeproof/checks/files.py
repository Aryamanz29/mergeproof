"""Which files a change must, may, or must not touch."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mergeproof import patterns
from mergeproof.checks.base import Check, fail, ok
from mergeproof.context import Context
from mergeproof.report import Outcome


class FilesChanged(Check):
    id = "files.changed"
    description = "The set of changed files satisfies any_of / all_of / none_of globs."

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        any_of: list[str] = Field(default_factory=list, description="At least one changed file matches")
        all_of: list[str] = Field(default_factory=list, description="Every glob matches at least one changed file")
        none_of: list[str] = Field(default_factory=list, description="No changed file matches")

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        paths = [f.path for f in ctx.files]
        problems: list[str] = []
        if params.any_of and not any(patterns.matches_any(params.any_of, p) for p in paths):
            problems.append("expected a change to " + " or ".join(params.any_of))
        for glob in params.all_of:
            if not any(patterns.match(glob, p) for p in paths):
                problems.append(f"expected a change to {glob}")
        forbidden = [p for p in paths if patterns.matches_any(params.none_of, p)]
        if forbidden:
            problems.append("must not change " + ", ".join(forbidden[:5]))
        if problems:
            return fail("; ".join(problems), fix=self.explain(params))
        return ok("changed files satisfy the rule")

    def explain(self, params: Params) -> str:
        parts = []
        if params.any_of:
            parts.append("change at least one of " + ", ".join(f"`{g}`" for g in params.any_of))
        if params.all_of:
            parts.append("change " + " and ".join(f"`{g}`" for g in params.all_of))
        if params.none_of:
            parts.append("leave " + ", ".join(f"`{g}`" for g in params.none_of) + " untouched")
        text = "; ".join(parts)
        return text[:1].upper() + text[1:] + "."
