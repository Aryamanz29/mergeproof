"""A structured verdict posted by an automated reviewer.

LLM reviewers are welcome as witnesses, not as the gate. They post a fenced
``verdict`` block; this check reads it, restricts who may post it, binds it
to the head commit, and turns it into an ordinary requirement next to the
deterministic ones::

    ```verdict
    check: trace-review
    verdict: pass
    head: b3ca7be
    confidence: 0.9
    summary: the after-run shows the corrected output; the before-run does not.
    ```
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mergeproof import evidence
from mergeproof.checks.base import Check, fail, ok, pending
from mergeproof.context import Context
from mergeproof.report import Outcome


class AgentVerdict(Check):
    id = "agent.verdict"
    description = "An allowed automated reviewer posted a verdict block for the named check."
    needs_github = True

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        name: str = Field(description="Value of `check:` inside the verdict block")
        authors: list[str] = Field(
            default_factory=list, description="Logins allowed to post it, e.g. github-actions[bot]"
        )
        bind_to_head: bool = True
        min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
        block: str = "verdict"

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        if not ctx.online:
            return pending(f"the `{params.name}` verdict is only visible in GitHub mode")
        latest: dict[str, Any] | None = None
        latest_at = ""
        rejected: list[str] = []
        for comment in ctx.comments:
            block = evidence.parse(comment.body, params.block)
            if not block.found or block.get("check") != params.name:
                continue
            if params.authors and comment.author not in params.authors:
                rejected.append(f"{comment.author}: not an allowed verdict author")
                continue
            head = str(block.get("head", ""))[:7]
            if params.bind_to_head and ctx.head_short and head != ctx.head_short:
                rejected.append(
                    f"{comment.author}: verdict is for {head or 'an unknown commit'}, head is {ctx.head_short}"
                )
                continue
            if comment.created_at >= latest_at:
                latest, latest_at = block.data, comment.created_at
        if latest is None:
            return pending(f"no `{params.name}` verdict for {ctx.head_short or 'this commit'}", details=rejected)
        verdict = str(latest.get("verdict", "")).lower()
        confidence = float(latest.get("confidence") or 1.0)
        summary = str(latest.get("summary", "")).strip()
        if verdict != "pass":
            return fail(
                f"verdict {verdict or 'missing'}: {summary}", data=latest, fix="Address the findings and push again."
            )
        if confidence < params.min_confidence:
            return pending(
                f"passed with confidence {confidence:.2f}, below {params.min_confidence:.2f}: {summary}", data=latest
            )
        return ok(f"verdict pass ({confidence:.2f}): {summary}", data=latest)

    def explain(self, params: Params) -> str:
        who = ", ".join(f"`{a}`" for a in params.authors) or "an automated reviewer"
        text = f"{who} posts a ```{params.block} block with `check: {params.name}` and `verdict: pass`"
        if params.bind_to_head:
            text += " for the current head sha"
        if params.min_confidence:
            text += f" with confidence of at least {params.min_confidence}"
        return text + "."
