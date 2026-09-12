"""evidence.field - a key in the PR's evidence block must be present and valid."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..context import PRContext
from ..models import CheckResult
from .base import Check, failed, passed


class EvidenceField(Check):
    id = "evidence.field"
    description = "A field in the fenced `evidence` block of the PR description must be present and valid."

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")
        key: str = Field(description="Dotted path inside the evidence block, e.g. `tenant` or `image.tag`")
        equals: Any | None = None
        one_of: list[Any] | None = None
        matches: str | None = Field(default=None, description="Regex the (string) value must match")
        min_items: int | None = Field(default=None, description="For list values")
        example: Any | None = Field(default=None, description="Placeholder shown in the evidence template")
        block: str = "evidence"

    def run(self, ctx: PRContext, params: Params, files: list[str]) -> CheckResult:
        ev = ctx.evidence(params.block)
        if ev.errors:
            return failed("evidence block could not be parsed", details=ev.errors, fix=self._fix(params))
        if not ev.has(params.key):
            why = (
                "no evidence block in PR description" if not ev.found else f"`{params.key}` missing from evidence block"
            )
            return failed(why, fix=self._fix(params))
        value = ev.get(params.key)
        if params.equals is not None and value != params.equals:
            return failed(f"`{params.key}` is {value!r}, expected {params.equals!r}", fix=self._fix(params))
        if params.one_of is not None and value not in params.one_of:
            return failed(f"`{params.key}` is {value!r}, expected one of {params.one_of!r}", fix=self._fix(params))
        if params.matches is not None:
            if not isinstance(value, str) or not re.search(params.matches, value):
                return failed(f"`{params.key}` does not match `{params.matches}`", fix=self._fix(params))
        if params.min_items is not None:
            if not isinstance(value, list) or len(value) < params.min_items:
                return failed(f"`{params.key}` needs at least {params.min_items} item(s)", fix=self._fix(params))
        shown = value if not isinstance(value, (dict, list)) else f"{type(value).__name__}[{len(value)}]"
        return passed(f"`{params.key}` = {shown}")

    def _fix(self, params: Params) -> str:
        return f"Add `{params.key}` to the ```{params.block} block in the PR description. " + self.explain(params)

    def explain(self, params: Params) -> str:
        parts = [f"`{params.key}` present"]
        if params.equals is not None:
            parts.append(f"equal to `{params.equals}`")
        if params.one_of:
            parts.append("one of " + ", ".join(f"`{v}`" for v in params.one_of))
        if params.matches:
            parts.append(f"matching `{params.matches}`")
        if params.min_items:
            parts.append(f"with ≥{params.min_items} item(s)")
        return " and ".join(parts) + "."

    def evidence_template(self, params: Params) -> dict[str, Any]:
        if params.example is not None:
            leaf: Any = params.example
        elif params.equals is not None:
            leaf = params.equals
        elif params.one_of:
            leaf = params.one_of[0]
        elif params.min_items:
            leaf = ["<item>"]
        else:
            leaf = "<value>"
        out: dict[str, Any] = {}
        cur = out
        keys = params.key.split(".")
        for k in keys[:-1]:
            cur = cur.setdefault(k, {})
        cur[keys[-1]] = leaf
        return out
