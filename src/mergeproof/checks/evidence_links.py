"""Before/after link pairs proving a behaviour change on a live system.

The links can point anywhere: a tracing backend, a dashboard, a CI run, a
screenshot bucket. ``pattern`` decides what counts as a valid link and may
capture named groups; ``verify`` names a verifier that resolves each link.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mergeproof.checks.base import Check, error, fail, ok, plural
from mergeproof.context import Context
from mergeproof.report import Outcome
from mergeproof.verifiers import UnknownVerifier, Verification, Verifier, as_verification, load_verifier

ANY_URL = r"^https?://\S+$"


class EvidenceLinks(Check):
    id = "evidence.links"
    description = "The evidence block lists before/after link pairs, optionally verified against their source."

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
        ev = ctx.evidence(params.block)
        if ev.errors:
            return fail("evidence block could not be parsed", details=ev.errors, fix=self.fix(params))
        items = ev.get(params.key)
        if not isinstance(items, list) or not items:
            return fail(f"no `{params.key}` list in the evidence block", fix=self.fix(params))

        regex = re.compile(params.pattern)
        problems: list[str] = []
        pairs: list[dict[str, str]] = []
        for index, item in enumerate(items, 1):
            if not isinstance(item, dict):
                problems.append(f"item {index}: expected a mapping with `before` and `after`")
                continue
            pair: dict[str, str] = {}
            for side in ("before", "after"):
                url = item.get(side)
                if not url:
                    if side == "after" or params.require_before:
                        problems.append(f"item {index}: missing `{side}`")
                    continue
                if not regex.match(str(url)):
                    problems.append(f"item {index}: `{side}` does not look like an accepted link")
                    continue
                pair[side] = str(url)
            if params.distinct and pair.get("before") and pair.get("before") == pair.get("after"):
                problems.append(f"item {index}: `before` and `after` are the same link")
            if "after" in pair and ("before" in pair or not params.require_before):
                pairs.append(pair)
        if problems:
            return fail(f"{plural(len(problems), 'problem')} in `{params.key}`", details=problems, fix=self.fix(params))
        if len(pairs) < params.min_pairs:
            return fail(f"{plural(len(pairs), 'valid pair')}, need {params.min_pairs}", fix=self.fix(params))

        if params.verify:
            verified = self.verify_pairs(pairs, regex, params)
            if verified is None:
                return error(f"verifier {params.verify!r} is not available or failed")
            unresolved = [line for line, v in verified if v is None or not v.found]
            if unresolved:
                return fail("link(s) could not be verified", details=unresolved, fix=self.fix(params))
            return ok(
                f"{plural(len(pairs), 'before/after pair')}, all verified",
                details=[line for line, _ in verified],
                data={"pairs": pairs, "verified": [v.model_dump(exclude_none=True) for _, v in verified if v]},
            )
        return ok(plural(len(pairs), "before/after pair"), data={"pairs": pairs})

    def verify_pairs(
        self, pairs: list[dict[str, str]], regex: re.Pattern[str], params: Params
    ) -> list[tuple[str, Verification | None]] | None:
        """One (line, verification) per link, in order; None when the verifier itself is unusable.

        The line is what a person reads: `after: braintrust · mcp-internal · 14 spans · 2026-09-14T17:02Z`,
        or the reason a link did not resolve. The verification is None when the verifier raised.
        """
        verifier = self.verifier
        if verifier is None:
            try:
                verifier = load_verifier(params.verify or "", params.verify_options)
            except (UnknownVerifier, TypeError, ValueError):
                return None
        results: list[tuple[str, Verification | None]] = []
        for pair in pairs:
            for side, url in pair.items():
                match = regex.match(url)
                assert match is not None
                try:
                    verification = as_verification(verifier.verify(url, match), params.verify or "")
                except Exception as exc:
                    results.append((f"{side}: {type(exc).__name__} while verifying {url}", None))
                    continue
                if verification.found:
                    results.append((f"{side}: {verification.line()}", verification))
                else:
                    results.append((f"{side}: not found at {url}", verification))
        return results

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
