from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from mergeproof.checks.base import Check, fail, ok
from mergeproof.context import Context
from mergeproof.report import Outcome


class Body(Check):
    id = "pr.body"
    description = "The PR description has the required sections, matches a regex, and meets a minimum length."

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        sections: list[str] = Field(default_factory=list, description="Markdown headings that must exist")
        matches: str | None = None
        min_length: int = 0

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        body = ctx.body or ""
        problems = [
            f"missing section `## {section}`"
            for section in params.sections
            if not re.search(rf"^#{{1,6}}\s*{re.escape(section)}\b", body, re.I | re.M)
        ]
        if params.matches and not re.search(params.matches, body, re.S):
            problems.append(f"description does not match `{params.matches}`")
        if len(body.strip()) < params.min_length:
            problems.append(f"description shorter than {params.min_length} characters")
        if problems:
            return fail("; ".join(problems), fix=self.explain(params))
        return ok("description ok")

    def explain(self, params: Params) -> str:
        parts = []
        if params.sections:
            parts.append("sections " + ", ".join(f"`## {s}`" for s in params.sections))
        if params.matches:
            parts.append(f"text matching `{params.matches}`")
        if params.min_length:
            parts.append(f"at least {params.min_length} characters")
        return "A PR description with " + "; ".join(parts) + "."
