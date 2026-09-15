"""Artifacts in the evidence block: links a reviewer can open, of a declared kind.

Three kinds cover what people actually paste into a pull request:

* ``pair``: a ``before`` and an ``after`` showing a behaviour change (traces, screenshots);
* ``single``: one link (a preview deployment, a dashboard, a report);
* ``set``: a list of links (screenshots of every screen touched, one log per environment).

``pattern`` decides what counts as an acceptable link and may capture named groups; ``verify``
names a verifier that resolves each link at its source and says what it found. That machinery
is shared with ``evidence.links``, which is this check with ``kind: pair``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mergeproof.checks.base import Check, error, fail, ok, plural
from mergeproof.context import Context
from mergeproof.report import Outcome
from mergeproof.verifiers import UnknownVerifier, Verification, Verifier, as_verification, load_verifier

ANY_URL = r"^https?://\S+$"
Kind = Literal["pair", "single", "set"]
NOUN = {"pair": "before/after pair", "single": "link", "set": "link"}


@dataclass
class Spec:
    """What one evaluation needs to know, whichever check asked for it."""

    key: str
    kind: Kind
    block: str
    pattern: str
    min_items: int
    require_before: bool
    distinct: bool
    verify: str | None
    verify_options: dict[str, Any]
    fix: str


def evaluate(ctx: Context, spec: Spec, verifier: Verifier | None = None) -> Outcome:
    ev = ctx.evidence(spec.block)
    if ev.errors:
        return fail("evidence block could not be parsed", details=ev.errors, fix=spec.fix)
    value = ev.get(spec.key)
    if value is None or value == [] or value == "":
        what = "value" if spec.kind == "single" else "list"
        return fail(f"no `{spec.key}` {what} in the evidence block", fix=spec.fix)

    regex = re.compile(spec.pattern)
    entries, problems = collect(spec, value, regex)
    if problems:
        return fail(f"{plural(len(problems), 'problem')} in `{spec.key}`", details=problems, fix=spec.fix)
    count = len(entries) if spec.kind != "pair" else len({e.item for e in entries})
    noun = NOUN[spec.kind]
    if count < spec.min_items:
        return fail(f"{plural(count, f'valid {noun}')}, need {spec.min_items}", fix=spec.fix)

    data: dict[str, Any] = {"pairs": pairs_of(entries)} if spec.kind == "pair" else {"links": [e.url for e in entries]}
    if not spec.verify:
        return ok(plural(count, noun), data=data)
    verified = verify_all(entries, regex, spec, verifier)
    if verified is None:
        return error(f"verifier {spec.verify!r} is not available or failed")
    unresolved = [line for line, v in verified if v is None or not v.found]
    if unresolved:
        return fail("link(s) could not be verified", details=unresolved, fix=spec.fix)
    data["verified"] = [v.model_dump(exclude_none=True) for _, v in verified if v]
    details = pair_lines(entries, verified) if spec.kind == "pair" else [line for line, _ in verified]
    return ok(f"{plural(count, noun)}, all verified", details=details, data=data)


def pair_lines(entries: list[Entry], verified: list[tuple[str, Verification | None]]) -> list[str]:
    """One line per before/after pair, with the URLs behind short links.

    A pair used to render as two lines carrying full URLs, so three pairs
    overflowed the report's detail cap and the reader was told "and 2 more"
    about the very evidence they are asked to open. One line per pair fits,
    and the descriptor is kept once rather than repeated for each side.
    """
    by_item: dict[int, dict[str, tuple[str, str]]] = {}
    for entry, (line, _) in zip(entries, verified, strict=False):
        text = line.split(": ", 1)[1] if ": " in line else line
        text = text.split(" — ")[0].strip()
        by_item.setdefault(entry.item, {})[entry.label] = (entry.url, text)
    out: list[str] = []
    for i, item in enumerate(sorted(by_item), start=1):
        sides = by_item[item]
        # Prefer the fuller descriptor: the two sides usually agree, and when they
        # do not the longer one carries the span count and timestamp.
        descriptor = max((t for _, t in sides.values()), key=len, default="")
        links = " · ".join(f"[{label}]({url})" for label, (url, _) in sorted(sides.items(), reverse=True))
        out.append(f"{i}. {descriptor} — {links}" if descriptor else f"{i}. {links}")
    return out


@dataclass
class Entry:
    item: int
    label: str  # `before`, `after`, or `link 2`
    url: str


def collect(spec: Spec, value: Any, regex: re.Pattern[str]) -> tuple[list[Entry], list[str]]:
    """Pull the links out of the evidence value for this kind; report what does not fit the shape."""
    entries: list[Entry] = []
    problems: list[str] = []

    def accept(item: int, label: str, url: Any, where: str) -> bool:
        if not url:
            problems.append(f"{where}: missing `{label}`" if spec.kind == "pair" else f"{where}: missing `url`")
            return False
        if not regex.match(str(url)):
            problems.append(f"{where}: `{label}` does not look like an accepted link")
            return False
        entries.append(Entry(item, label, str(url)))
        return True

    if spec.kind == "single":
        url = value.get("url") if isinstance(value, dict) else value
        if isinstance(value, list | tuple):
            problems.append(f"`{spec.key}`: expected one link, got a list")
        else:
            accept(1, spec.key, url, f"`{spec.key}`")
        return entries, problems

    if not isinstance(value, list):
        problems.append(f"`{spec.key}`: expected a list")
        return entries, problems
    for index, item in enumerate(value, 1):
        where = f"item {index}"
        if spec.kind == "set":
            url = item.get("url") if isinstance(item, dict) else item
            if isinstance(item, list | dict) and not isinstance(item, dict):
                problems.append(f"{where}: expected a link or a mapping with `url`")
                continue
            accept(index, f"link {index}", url, where)
            continue
        if not isinstance(item, dict):
            problems.append(f"{where}: expected a mapping with `before` and `after`")
            continue
        got: dict[str, str] = {}
        for side in ("before", "after"):
            url = item.get(side)
            if not url and side == "before" and not spec.require_before:
                continue
            if accept(index, side, url, where):
                got[side] = str(url)
        if spec.distinct and got.get("before") and got.get("before") == got.get("after"):
            problems.append(f"{where}: `before` and `after` are the same link")
    return entries, problems


def pairs_of(entries: list[Entry]) -> list[dict[str, str]]:
    pairs: dict[int, dict[str, str]] = {}
    for e in entries:
        pairs.setdefault(e.item, {})[e.label] = e.url
    return [pairs[k] for k in sorted(pairs)]


def verify_all(
    entries: list[Entry], regex: re.Pattern[str], spec: Spec, verifier: Verifier | None
) -> list[tuple[str, Verification | None]] | None:
    """One (line, verification) per link, in order; None when the verifier itself is unusable.

    The line is what a person reads: `after: braintrust · mcp-internal · 14 spans · 2026-09-14T17:02Z`,
    or the reason a link did not resolve. The verification is None when the verifier raised.
    """
    if verifier is None:
        try:
            verifier = load_verifier(spec.verify or "", spec.verify_options)
        except (UnknownVerifier, TypeError, ValueError):
            return None
    results: list[tuple[str, Verification | None]] = []
    for e in entries:
        match = regex.match(e.url)
        assert match is not None
        try:
            verification = as_verification(verifier.verify(e.url, match), spec.verify or "")
        except Exception as exc:
            results.append((f"{e.label}: {type(exc).__name__} while verifying {e.url}", None))
            continue
        if verification.found:
            # The URL rides the line so a reviewer can open the evidence straight from the
            # report — the failure branches below already do this; success did not, which left
            # the one audience that must click the links with nothing to click.
            results.append((f"{e.label}: {verification.line()} — {e.url}", verification))
        else:
            results.append((f"{e.label}: not found at {e.url}", verification))
    return results


class EvidenceArtifacts(Check):
    id = "evidence.artifacts"
    description = "The evidence block lists artifacts of a kind: before/after pairs, one link, or a set of links."

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        key: str = "artifacts"
        kind: Kind = Field(default="pair", description="`pair` (before/after), `single` (one link) or `set` (a list)")
        min_items: int = Field(default=1, description="Pairs for `pair`, links for `set`; ignored for `single`")
        pattern: str = Field(
            default=ANY_URL, description="Regex a link must match; named groups are passed to the verifier"
        )
        require_before: bool = Field(default=True, description="`pair` only: require `before` as well as `after`")
        distinct: bool = Field(default=True, description="`pair` only: `before` and `after` must differ")
        verify: str | None = Field(default=None, description="Verifier name: `http` or one provided by a plugin")
        verify_options: dict[str, Any] = Field(default_factory=dict)
        example: str = Field(default="https://<host>/<path-to-artifact>", description="Placeholder in the template")
        block: str = "evidence"

    verifier: Verifier | None = None

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        return evaluate(ctx, self.spec(params), self.verifier)

    def spec(self, params: Params) -> Spec:
        return Spec(
            key=params.key,
            kind=params.kind,
            block=params.block,
            pattern=params.pattern,
            min_items=1 if params.kind == "single" else params.min_items,
            require_before=params.require_before,
            distinct=params.distinct,
            verify=params.verify,
            verify_options=params.verify_options,
            fix=self.fix(params),
        )

    def fix(self, params: Params) -> str:
        key = params.key
        if params.kind == "pair":
            return (
                "Capture a link showing the behaviour before the change and one after it; "
                f"list them as `before`/`after` pairs under `{key}` in the evidence block."
            )
        if params.kind == "single":
            return f"Put the link under `{key}` in the evidence block."
        return f"List the links under `{key}` in the evidence block, one per item."

    def explain(self, params: Params) -> str:
        key = params.key
        if params.kind == "pair":
            text = f"At least {params.min_items} `before`/`after` link pair(s) under `{key}` in the evidence block"
        elif params.kind == "single":
            text = f"A link under `{key}` in the evidence block"
        else:
            text = f"At least {plural(params.min_items, 'link')} under `{key}` in the evidence block"
        if params.pattern != ANY_URL:
            each = "" if params.kind == "single" else "each "
            text += f", {each}matching `{params.pattern}`"
        if params.verify:
            text += f"; links are verified with `{params.verify}`"
        return text + "."

    def evidence_template(self, params: Params) -> dict[str, Any]:
        what = "<what was exercised>"
        if params.kind == "single":
            return {params.key: {"what": what, "url": params.example}}
        if params.kind == "set":
            return {params.key: [{"what": what, "url": params.example}]}
        pair = {"before": params.example, "after": params.example}
        if not params.require_before:
            pair = {"after": params.example}
        return {params.key: [{"what": what, **pair}]}
