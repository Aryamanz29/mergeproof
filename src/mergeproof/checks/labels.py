from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mergeproof.checks.base import Check, fail, ok
from mergeproof.context import Context
from mergeproof.report import Outcome


class Labels(Check):
    id = "pr.labels"
    description = "PR labels satisfy any_of / all_of / none_of."

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        any_of: list[str] = Field(default_factory=list)
        all_of: list[str] = Field(default_factory=list)
        none_of: list[str] = Field(default_factory=list)

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        have = set(ctx.labels)
        problems: list[str] = []
        if params.any_of and not have & set(params.any_of):
            problems.append("needs one of " + ", ".join(params.any_of))
        missing = sorted(set(params.all_of) - have)
        if missing:
            problems.append("missing " + ", ".join(missing))
        banned = sorted(have & set(params.none_of))
        if banned:
            problems.append("must not have " + ", ".join(banned))
        if problems:
            return fail("; ".join(problems), fix=self.explain(params))
        return ok("labels: " + (", ".join(sorted(have)) or "none"))

    def explain(self, params: Params) -> str:
        parts = []
        if params.any_of:
            parts.append("any of " + ", ".join(f"`{x}`" for x in params.any_of))
        if params.all_of:
            parts.append("all of " + ", ".join(f"`{x}`" for x in params.all_of))
        if params.none_of:
            parts.append("none of " + ", ".join(f"`{x}`" for x in params.none_of))
        return "Labels: " + "; ".join(parts) + "."
