"""A human other than the author attests to having checked the evidence.

Agents can write tests and paste links; the one thing they must not do is
approve their own evidence. By default the attestation is bound to the head
commit so that a later push invalidates it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mergeproof.checks.base import Check, ok, pending
from mergeproof.context import Context
from mergeproof.report import Outcome


class HumanVerified(Check):
    id = "review.human_verified"
    description = "A reviewer other than the author posted the verification phrase after checking the evidence."
    needs_github = True

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        phrase: str = "/verified"
        allowed_users: list[str] = Field(default_factory=list, description="Empty means any non-author human")
        exclude_author: bool = True
        bind_to_head: bool = Field(default=True, description="The comment must contain the 7-character head sha")
        require_review_state: str | None = Field(default=None, description="For example APPROVED")

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        if not ctx.online:
            return pending("reviewer verification is only visible in GitHub mode")
        expected = f"{params.phrase} {ctx.head_short}".strip() if params.bind_to_head else params.phrase
        rejected: list[str] = []
        for comment in ctx.comments:
            if params.phrase not in comment.body:
                continue
            if comment.is_bot:
                rejected.append(f"{comment.author}: bots cannot verify")
            elif params.exclude_author and comment.author == ctx.author:
                rejected.append(f"{comment.author}: the author cannot self-verify")
            elif params.allowed_users and comment.author not in params.allowed_users:
                rejected.append(f"{comment.author}: not an allowed verifier")
            elif params.bind_to_head and ctx.head_short and ctx.head_short not in comment.body:
                rejected.append(f"{comment.author}: verified an older commit, needs `{expected}`")
            elif params.require_review_state and comment.state != params.require_review_state:
                rejected.append(f"{comment.author}: must be a {params.require_review_state} review")
            else:
                return ok(
                    f"verified by @{comment.author}",
                    details=[comment.url] if comment.url else [],
                    data={"by": comment.author, "at": comment.created_at},
                )
        return pending(f"waiting for a reviewer to post `{expected}`", details=rejected, fix=self.explain(params))

    def explain(self, params: Params) -> str:
        who = (
            ("one of " + ", ".join(f"@{u}" for u in params.allowed_users))
            if params.allowed_users
            else "a reviewer other than the author"
        )
        tail = " followed by the 7-character head sha" if params.bind_to_head else ""
        state = f" as an {params.require_review_state} review" if params.require_review_state else ""
        return f"After checking the evidence, {who} comments `{params.phrase}`{tail}{state}."
