"""Replay a policy against pull requests that already merged.

Tightening a policy is scary because nobody knows what it would have
blocked. Replay answers that with data: it rebuilds the context of each
merged pull request from the API, evaluates the candidate policy against
it, and says which would have been blocked and by what. Nothing is posted.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mergeproof import engine
from mergeproof.checks.registry import Registry
from mergeproof.context import Context
from mergeproof.policy import Policy
from mergeproof.providers.github import Client, fetch
from mergeproof.report import Report, Status

Fetcher = Callable[[Client, str, int], Context]


def merged_pulls(client: Client, repo: str, last: int = 50, since: str | None = None) -> list[dict[str, Any]]:
    """The most recently merged pull requests, newest first: number, title, merged_at, merged_by."""
    found: list[dict[str, Any]] = []
    page = 1
    while len(found) < last:
        batch = client.get(
            f"/repos/{repo}/pulls", state="closed", sort="updated", direction="desc", per_page=100, page=page
        )
        if not batch:
            break
        for pr in batch:
            merged_at = pr.get("merged_at")
            if not merged_at or (since and merged_at < since):
                continue
            found.append(
                {
                    "number": pr["number"],
                    "title": pr.get("title") or "",
                    "merged_at": merged_at,
                    "merged_by": (pr.get("merged_by") or pr.get("user") or {}).get("login", ""),
                }
            )
        if len(batch) < 100:
            break
        page += 1
    found.sort(key=lambda p: p["merged_at"], reverse=True)
    return found[:last]


@dataclass
class Row:
    number: int
    title: str
    merged_at: str
    report: Report
    against: Report | None = None
    context: Context | None = None
    error: str | None = None

    @property
    def verdict(self) -> Status:
        return self.report.verdict

    @property
    def blocking(self) -> list[str]:
        return [f"{rule.id} · {req.label}" for rule, req in self.report.blocking_unmet()]

    @property
    def changed(self) -> bool:
        return self.against is not None and self.against.verdict != self.report.verdict


@dataclass
class Replay:
    rows: list[Row] = field(default_factory=list)

    @property
    def would_block(self) -> list[Row]:
        return [r for r in self.rows if r.verdict in (Status.FAIL, Status.PENDING)]

    @property
    def applied(self) -> list[Row]:
        return [r for r in self.rows if r.report.matched]


def replay(
    client: Client,
    repo: str,
    pulls: Iterable[dict[str, Any]],
    candidate: Policy,
    registry: Registry,
    against: Policy | None = None,
    fetcher: Fetcher | None = None,
    progress: Callable[[str], None] | None = None,
) -> Replay:
    build = fetcher or fetch
    result = Replay()
    for pr in pulls:
        number = int(pr["number"])
        if progress:
            progress(f"#{number} {pr.get('title', '')}")
        try:
            ctx = build(client, repo, number)
        except Exception as exc:
            result.rows.append(
                Row(
                    number, pr.get("title", ""), pr.get("merged_at", ""), Report(), error=f"{type(exc).__name__}: {exc}"
                )
            )
            continue
        report = engine.evaluate(candidate, ctx, registry)
        baseline = engine.evaluate(against, ctx, registry) if against else None
        result.rows.append(Row(number, pr.get("title", ""), pr.get("merged_at", ""), report, baseline, ctx))
    return result


def save_scenarios(result: Replay, folder: Path) -> list[Path]:
    """Write one scenario file per pull request, in the shape the examples and the integration suite use."""
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for row in result.rows:
        if row.context is None:
            continue
        path = folder / f"pr-{row.number}.json"
        doc = {"expected": row.verdict.value, "context": json.loads(row.context.to_json())}
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def render_text(result: Replay, repo: str) -> str:
    rows = result.rows
    if not rows:
        return "no merged pull requests to replay"
    width = max(len(str(r.number)) for r in rows) + 1
    lines = []
    for r in rows:
        mark = f"#{r.number}".rjust(width)
        day = r.merged_at[:10]
        if r.error:
            lines.append(f"{mark}  {day}  error    {r.title[:50]}\n{' ' * (width + 2)}{r.error}")
            continue
        verdict = r.verdict.value.ljust(7)
        arrow = f"  (was {r.against.verdict.value})" if r.changed and r.against else ""
        lines.append(f"{mark}  {day}  {verdict}  {r.title[:50]}{arrow}")
        for item in r.blocking:
            lines.append(f"{' ' * (width + 2)}needs  {item}")
    blocked = result.would_block
    summary = (
        f"\n{len(rows)} merged pull requests in {repo}; the policy applied to {len(result.applied)}"
        f" and would have blocked {len(blocked)}"
    )
    if any(r.against for r in rows):
        newly = [r for r in blocked if r.against and r.against.verdict not in (Status.FAIL, Status.PENDING)]
        summary += f", {len(newly)} of them not blocked by the policy compared against"
    counts: dict[str, int] = {}
    for r in blocked:
        for item in r.blocking:
            counts[item] = counts.get(item, 0) + 1
    if counts:
        summary += "\nmost common blockers:"
        for item, n in sorted(counts.items(), key=lambda kv: -kv[1])[:5]:
            summary += f"\n  {n:>3}  {item}"
    return "\n".join(lines) + summary + "\n"


def render_json(result: Replay) -> str:
    return json.dumps(
        [
            {
                "number": r.number,
                "title": r.title,
                "merged_at": r.merged_at,
                "verdict": r.verdict.value if not r.error else "error",
                "against": r.against.verdict.value if r.against else None,
                "blocking": r.blocking,
                "error": r.error,
            }
            for r in result.rows
        ],
        indent=2,
    )
