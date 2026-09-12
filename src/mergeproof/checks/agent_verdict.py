"""agent.verdict - a structured verdict posted by an automated reviewer (LLM agent) on the PR.

Non-deterministic reviewers (GitHub Copilot agents, Claude Code Action, an in-house review agent)
are welcome, but they are *witnesses*, not the gate. They post a fenced ``verdict`` block; this
check reads it, binds it to the head sha, restricts who may post it, and turns it into an
ordinary pass/fail/pending requirement next to the deterministic ones::

    <!-- mergeproof-verdict -->
    ```verdict
    check: trace-review
    verdict: pass          # pass | fail
    head: b3ca7be
    confidence: 0.9
    summary: after-trace shows auto_corrections populated; before-trace shows none.
    ```
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..context import PRContext
from ..evidence import parse_evidence
from ..models import CheckResult
from .base import Check, failed, passed, pending


class AgentVerdict(Check):
    id = "agent.verdict"
    description = (
        "A structured `verdict` block posted on the PR by an allowed automated reviewer for the given check name."
    )
    needs_github = True

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str = Field(description="Value of `check:` inside the verdict block, e.g. trace-review")
        authors: list[str] = Field(
            default_factory=list, description="Logins allowed to post it (e.g. github-actions[bot])"
        )
        bind_to_head: bool = True
        min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
        block: str = "verdict"
        stale: str = Field(
            default="pending", pattern="^(pending|fail)$", description="Status when only older verdicts exist"
        )

    def run(self, ctx: PRContext, params: Params, files: list[str]) -> CheckResult:
        if not ctx.online:
            return pending(f"agent verdict `{params.name}` is only visible in GitHub mode")
        latest: dict[str, Any] | None = None
        latest_at = ""
        rejected: list[str] = []
        for c in ctx.comments():
            ev = parse_evidence(c.body, params.block)
            if not ev.found or ev.get("check") != params.name:
                continue
            if params.authors and c.author not in params.authors:
                rejected.append(f"{c.author}: not an allowed verdict author")
                continue
            if params.bind_to_head and ctx.head_short and str(ev.get("head", ""))[:7] != ctx.head_short:
                rejected.append(f"{c.author}: verdict is for `{ev.get('head')}`, head is `{ctx.head_short}`")
                continue
            if c.created_at >= latest_at:
                latest, latest_at = ev.data, c.created_at
        if latest is None:
            msg = f"no `{params.name}` verdict for {ctx.head_short or 'this head'}"
            return (
                failed(msg, details=rejected) if params.stale == "fail" and rejected else pending(msg, details=rejected)
            )
        verdict = str(latest.get("verdict", "")).lower()
        conf = float(latest.get("confidence", 1.0) or 0.0)
        summary = str(latest.get("summary", "")).strip()
        if verdict != "pass":
            return failed(
                f"agent verdict: {verdict or 'missing'} — {summary}",
                data=latest,
                fix="Address the reviewer's findings and push; the agent re-runs.",
            )
        if conf < params.min_confidence:
            return pending(
                f"agent passed with confidence {conf:.2f} < {params.min_confidence:.2f} — {summary}", data=latest
            )
        return passed(f"agent verdict: pass ({conf:.2f}) — {summary}", data=latest)

    def explain(self, params: Params) -> str:
        who = ", ".join(f"`{a}`" for a in params.authors) or "an automated reviewer"
        return (
            f"{who} posts a ```{params.block} block with `check: {params.name}`, `verdict: pass`"
            + (", `head: <sha7>`" if params.bind_to_head else "")
            + (f", confidence ≥ {params.min_confidence}" if params.min_confidence else "")
            + "."
        )
