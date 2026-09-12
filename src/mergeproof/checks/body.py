"""pr.body - free-text PR description requirements (sections, regex, length)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from ..context import PRContext
from ..models import CheckResult
from .base import Check, failed, passed


class Body(Check):
    id = "pr.body"
    description = "PR description must contain required sections / match a regex / meet a minimum length."

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")
        sections: list[str] = Field(default_factory=list, description="Markdown headings that must exist")
        matches: str | None = None
        min_length: int = 0

    def run(self, ctx: PRContext, params: Params, files: list[str]) -> CheckResult:
        body = ctx.body or ""
        problems = []
        for s in params.sections:
            if not re.search(rf"^#{{1,6}}\s*{re.escape(s)}\b", body, re.I | re.M):
                problems.append(f"missing section `## {s}`")
        if params.matches and not re.search(params.matches, body, re.S):
            problems.append(f"body does not match `{params.matches}`")
        if len(body.strip()) < params.min_length:
            problems.append(f"body shorter than {params.min_length} chars")
        if problems:
            return failed("; ".join(problems), fix=self.explain(params))
        return passed("description ok")

    def explain(self, params: Params) -> str:
        parts = []
        if params.sections:
            parts.append("sections " + ", ".join(f"`## {s}`" for s in params.sections))
        if params.matches:
            parts.append(f"text matching `{params.matches}`")
        if params.min_length:
            parts.append(f"≥{params.min_length} characters")
        return "PR description with " + "; ".join(parts) + "."
