"""Before/after link pairs proving a behaviour change on a live system.

This is ``evidence.artifacts`` with ``kind: pair`` and its own parameter names, kept because
policies and the Langfuse and Braintrust plugins are written against it. The links can point
anywhere: a tracing backend, a dashboard, a CI run, a screenshot bucket.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mergeproof.checks.base import Check
from mergeproof.checks.evidence_artifacts import ANY_URL, Spec, evaluate
from mergeproof.context import Context
from mergeproof.report import Outcome
from mergeproof.verifiers import Verifier


class EvidenceLinks(Check):
    id = "evidence.links"
    description = (
        "The evidence block lists before/after link pairs, optionally verified against their source"
        " (the same as evidence.artifacts with kind: pair)."
    )

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        key: str = "links"
        min_pairs: int = 1
        pattern: str = Field(
            default=ANY_URL, description="Regex a link must match; named groups are passed to the verifier"
        )
        require_before: bool = True
        distinct: bool = Field(default=True, description="`before` and `after` must differ")
        verify: str | None = Field(default=None, description="Verifier name: `http` or one provided by a plugin")
        verify_options: dict[str, Any] = Field(default_factory=dict)
        example: str = Field(default="https://<host>/<path-to-run>", description="Placeholder in the evidence template")
        block: str = "evidence"

    verifier: Verifier | None = None

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        spec = Spec(
            key=params.key,
            kind="pair",
            block=params.block,
            pattern=params.pattern,
            min_items=params.min_pairs,
            require_before=params.require_before,
            distinct=params.distinct,
            verify=params.verify,
            verify_options=params.verify_options,
            fix=self.fix(params),
        )
        return evaluate(ctx, spec, self.verifier)

    def fix(self, params: Params) -> str:
        return (
            "Capture a link showing the behaviour before the change and one after it; "
            f"list them as `before`/`after` pairs under `{params.key}` in the evidence block."
        )

    def explain(self, params: Params) -> str:
        text = f"At least {params.min_pairs} `before`/`after` link pair(s) under `{params.key}` in the evidence block"
        if params.pattern != ANY_URL:
            text += f", each matching `{params.pattern}`"
        if params.verify:
            text += f"; links are verified with `{params.verify}`"
        return text + "."

    def evidence_template(self, params: Params) -> dict[str, Any]:
        pair = {"before": params.example, "after": params.example}
        if not params.require_before:
            pair = {"after": params.example}
        return {params.key: [{"what": "<what was exercised>", **pair}]}
