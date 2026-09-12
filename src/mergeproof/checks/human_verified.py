"""review.human_verified - a human other than the author attests they checked the evidence.

Agents can write tests and paste trace links; the one thing they must not do is approve their own
evidence. This check looks for a comment/review containing a phrase (default ``/verified``) from a
non-author, non-bot account, optionally bound to the current head sha so a later push invalidates it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..context import PRContext
from ..models import CheckResult
from .base import Check, passed, pending


class HumanVerified(Check):
    id = "review.human_verified"
    description = (
        "A reviewer other than the PR author must post a verification phrase after checking "
        "the evidence (e.g. opened the before/after traces)."
    )
    needs_github = True

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")
        phrase: str = "/verified"
        allowed_users: list[str] = Field(default_factory=list, description="Empty = any non-author human")
        exclude_author: bool = True
        bind_to_head: bool = Field(default=True, description="Comment must include the 7-char head sha")
        require_review_state: str | None = Field(default=None, description="e.g. APPROVED")

    def run(self, ctx: PRContext, params: Params, files: list[str]) -> CheckResult:
        if not ctx.online:
            return pending("reviewer verification is only visible in GitHub mode")
        want = f"{params.phrase} {ctx.head_short}" if params.bind_to_head else params.phrase
        rejected: list[str] = []
        for c in ctx.comments():
            if params.phrase not in c.body:
                continue
            if c.is_bot:
                rejected.append(f"{c.author}: bots cannot verify")
                continue
            if params.exclude_author and c.author == ctx.author:
                rejected.append(f"{c.author}: author cannot self-verify")
                continue
            if params.allowed_users and c.author not in params.allowed_users:
                rejected.append(f"{c.author}: not in allowed verifiers")
                continue
            if params.bind_to_head and ctx.head_short and ctx.head_short not in c.body:
                rejected.append(f"{c.author}: verification is for an older commit (needs `{want}`)")
                continue
            if params.require_review_state and c.state != params.require_review_state:
                rejected.append(f"{c.author}: must be a {params.require_review_state} review")
                continue
            return passed(
                f"verified by @{c.author}", details=[c.url] if c.url else [], data={"by": c.author, "at": c.created_at}
            )
        return pending(
            f"waiting for a reviewer to post `{want}`",
            details=rejected,
            fix=self.explain(params) + (f" Current head: `{ctx.head_short}`." if ctx.head_short else ""),
        )

    def explain(self, params: Params) -> str:
        who = (
            ("one of " + ", ".join(f"@{u}" for u in params.allowed_users))
            if params.allowed_users
            else "a reviewer other than the author"
        )
        sha = " followed by the 7-char head sha" if params.bind_to_head else ""
        state = f" as an {params.require_review_state} review" if params.require_review_state else ""
        return f"After checking the evidence, {who} comments `{params.phrase}`{sha}{state}."
