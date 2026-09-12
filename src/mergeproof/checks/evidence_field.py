"""A key in the evidence block is present and has an acceptable value."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mergeproof.checks.base import Check, fail, ok
from mergeproof.context import Context
from mergeproof.report import Outcome


class EvidenceField(Check):
    id = "evidence.field"
    description = "A field in the PR's evidence block is present and valid."

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        key: str = Field(description="Dotted path inside the evidence block, e.g. `environment` or `image.tag`")
        equals: Any | None = None
        one_of: list[Any] | None = None
        matches: str | None = Field(default=None, description="Regex a string value must match")
        min_items: int | None = Field(default=None, description="Minimum length for a list value")
        example: Any | None = Field(default=None, description="Placeholder shown in the evidence template")
        block: str = "evidence"

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        ev = ctx.evidence(params.block)
        if ev.errors:
            return fail("evidence block could not be parsed", details=ev.errors, fix=self.fix(params))
        if not ev.has(params.key):
            why = f"no `{params.block}` block in the PR description" if not ev.found else f"`{params.key}` is missing"
            return fail(why, fix=self.fix(params))
        value = ev.get(params.key)
        if params.equals is not None and value != params.equals:
            return fail(f"`{params.key}` is {value!r}, expected {params.equals!r}", fix=self.fix(params))
        if params.one_of is not None and value not in params.one_of:
            return fail(f"`{params.key}` is {value!r}, expected one of {params.one_of}", fix=self.fix(params))
        if params.matches is not None and (not isinstance(value, str) or not re.search(params.matches, value)):
            return fail(f"`{params.key}` does not match `{params.matches}`", fix=self.fix(params))
        if params.min_items is not None and (not isinstance(value, list) or len(value) < params.min_items):
            return fail(f"`{params.key}` needs at least {params.min_items} item(s)", fix=self.fix(params))
        shown = value if isinstance(value, str | int | float | bool) else f"{type(value).__name__}[{len(value)}]"
        return ok(f"`{params.key}` = {shown}")

    def fix(self, params: Params) -> str:
        return f"Add `{params.key}` to the `{params.block}` block in the PR description. {self.explain(params)}"

    def explain(self, params: Params) -> str:
        wants = [f"`{params.key}` present"]
        if params.equals is not None:
            wants.append(f"equal to `{params.equals}`")
        if params.one_of:
            wants.append("one of " + ", ".join(f"`{v}`" for v in params.one_of))
        if params.matches:
            wants.append(f"matching `{params.matches}`")
        if params.min_items:
            wants.append(f"with at least {params.min_items} item(s)")
        return " and ".join(wants) + "."

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
        template: dict[str, Any] = {}
        node = template
        *parents, last = params.key.split(".")
        for part in parents:
            node = node.setdefault(part, {})
        node[last] = leaf
        return template
