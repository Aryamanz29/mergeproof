"""A human other than the author attests to having checked the evidence.

Agents can write tests and paste links; the one thing they must not do is
approve their own evidence. The attestation is either the verification phrase
in a comment or, when the policy says so, an approving review. By default it
is bound to the head commit so that a later push invalidates it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mergeproof.checks.base import Check, ok, pending
from mergeproof.context import Comment, Context
from mergeproof.report import Outcome


class HumanVerified(Check):
    id = "review.human_verified"
    description = (
        "A reviewer other than the author verified the evidence: an approving review or the verification phrase."
    )
    needs_github = True

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        phrase: str = "/verified"
        accept_approval: bool = Field(
            default=False, description="An approving review on the head commit counts, without the phrase"
        )
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
            approval = params.accept_approval and comment.kind == "review" and comment.state == "APPROVED"
            if not approval and params.phrase not in comment.body:
                continue
            reason = self.ineligible(ctx, params, comment)
            if reason:
                rejected.append(f"{comment.author}: {reason}")
            elif approval and params.bind_to_head and ctx.head_sha and comment.commit != ctx.head_sha:
                rejected.append(f"{comment.author}: approved an older commit, approve again or post `{expected}`")
            elif not approval and params.bind_to_head and ctx.head_short and ctx.head_short not in comment.body:
                rejected.append(f"{comment.author}: verified an older commit, needs `{expected}`")
            elif not approval and params.require_review_state and comment.state != params.require_review_state:
                rejected.append(f"{comment.author}: must be a {params.require_review_state} review")
            else:
                how = "approved" if approval else "verified"
                return ok(
                    f"{how} by @{comment.author}",
                    details=[comment.url] if comment.url else [],
                    data={"by": comment.author, "at": comment.created_at, "how": how},
                )
        waiting = f"an approving review or `{expected}`" if params.accept_approval else f"`{expected}`"
        return pending(f"waiting for a reviewer to post {waiting}", details=rejected, fix=self.explain(params))

    @staticmethod
    def ineligible(ctx: Context, params: Params, comment: Comment) -> str | None:
        if comment.is_bot:
            return "bots cannot verify"
        if params.exclude_author and comment.author == ctx.author:
            return "the author cannot self-verify"
        if params.allowed_users and comment.author not in params.allowed_users:
            return "not an allowed verifier"
        return None

    def explain(self, params: Params) -> str:
        who = (
            ("one of " + ", ".join(f"@{u}" for u in params.allowed_users))
            if params.allowed_users
            else "a reviewer other than the author"
        )
        tail = " followed by the 7-character head sha" if params.bind_to_head else ""
        state = f" as an {params.require_review_state} review" if params.require_review_state else ""
        phrase = f"comments `{params.phrase}`{tail}{state}"
        if params.accept_approval:
            on = " of the current commit" if params.bind_to_head else ""
            return f"After checking the evidence, {who} approves the pull request{on}, or {phrase}."
        return f"After checking the evidence, {who} {phrase}."
