from __future__ import annotations

from mergeproof import evidence
from mergeproof.policy import Policy, Severity
from mergeproof.report import Report, Status

MARKER = "<!-- mergeproof-report -->"
BADGE_LOGO = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNTYgMjU2Ij48cGF0aCBkPSJNMTI4IDE4IEwyMTggNTAgVjEyNiBDMjE4IDE4NCAxNzggMjI0IDEyOCAyNDIgQzc4IDIyNCAzOCAxODQgMzggMTI2IFY1MCBaIiBmaWxsPSIjZmZmIi8+PHBhdGggZD0iTTkyIDg0IEM5MiAxMjYgMTI4IDExOCAxMjggMTY2IE0xNjQgODQgQzE2NCAxMjYgMTI4IDExOCAxMjggMTY2IiBmaWxsPSJub25lIiBzdHJva2U9IiM2ZDI4ZDkiIHN0cm9rZS13aWR0aD0iMTIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPjxjaXJjbGUgY3g9IjkyIiBjeT0iODIiIHI9IjE0IiBmaWxsPSIjNmQyOGQ5Ii8+PGNpcmNsZSBjeD0iMTY0IiBjeT0iODIiIHI9IjE0IiBmaWxsPSIjNmQyOGQ5Ii8+PGNpcmNsZSBjeD0iMTI4IiBjeT0iMTcyIiByPSIyNCIgZmlsbD0iIzZkMjhkOSIvPjxwYXRoIGQ9Ik0xMTYgMTcyIEwxMjUgMTgxIEwxNDEgMTYzIiBmaWxsPSJub25lIiBzdHJva2U9IiNmZmYiIHN0cm9rZS13aWR0aD0iOCIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+PC9zdmc+"  # noqa: E501
PROJECT_URL = "https://github.com/Aryamanz29/mergeproof"

ICON = {
    Status.PASS: "✅",
    Status.FAIL: "❌",
    Status.WARN: "⚠️",
    Status.PENDING: "⏳",
    Status.SKIP: "⏭️",
    Status.ERROR: "💥",
}

WORD = {
    Status.PASS: "Satisfied",
    Status.FAIL: "**Missing**",
    Status.WARN: "Warning",
    Status.PENDING: "Pending",
    Status.SKIP: "Not applicable",
    Status.ERROR: "**Error**",
}

BADGE_COLOR = {Status.PASS: "2ea043", Status.WARN: "dbab09", Status.PENDING: "dbab09", Status.FAIL: "cf222e"}


def badge(report: Report) -> str:
    """One image: the shield, the name, and the count, coloured by verdict."""
    total = len(report.requirements)
    counts = report.counts()
    done = counts[Status.PASS] + counts[Status.SKIP]
    value = f"{done}%2F{total}%20satisfied" if total else "no%20rules%20apply"
    color = BADGE_COLOR[report.verdict]
    return (
        f"![mergeproof: {done} of {total} satisfied]"
        f"(https://img.shields.io/badge/mergeproof-{value}-{color}?style=flat-square&labelColor=1f2328&logo={BADGE_LOGO})"
    )


def sentence(report: Report) -> str:
    total = len(report.requirements)
    counts = report.counts()
    done = counts[Status.PASS] + counts[Status.SKIP]
    where = ""
    if report.head_sha:
        repo_url = f"https://github.com/{report.repo}" if report.repo else PROJECT_URL
        where = f" for [`{report.head_sha[:7]}`]({repo_url}/commit/{report.head_sha})"
    if done == total:
        return f"**All {total} requirements are satisfied**{where}."
    tail = report.headline().split(" satisfied", 1)[1].lstrip(", ")
    return f"**{total - done} of {total} requirements need attention**{where}: {tail}."


def header(report: Report, run_url: str | None) -> str:
    links = []
    if report.repo and report.base_ref:
        links.append(f"[policy](https://github.com/{report.repo}/blob/{report.base_ref}/{report.policy_path})")
    if run_url:
        links.append(f"[details]({run_url})")
    links.append(f"[docs]({PROJECT_URL})")
    return f"{badge(report)} &nbsp;<sub>{' · '.join(links)}</sub>"


def report_markdown(report: Report, marker: bool = True, run_url: str | None = None) -> str:
    """The sticky PR comment: a header, one sentence, one table, next steps only when needed."""
    lines: list[str] = [MARKER] if marker else []
    lines += [header(report, run_url), ""]
    if not report.matched:
        lines.append("No rules apply to this change.")
        return "\n".join(lines)

    lines += [sentence(report), "", "| Requirement | Status | Detail |", "|:--|:--|:--|"]
    for rule in report.matched:
        for req in rule.requirements:
            label = f"**{req.label}**" + (" <sub>warn only</sub>" if req.severity != Severity.BLOCK else "")
            lines.append(f"| {label}<br><sub>{rule.id}</sub> | {WORD[req.effective]} | {req.outcome.summary} |")
    lines.append("")

    blocking = report.blocking_unmet()
    if blocking:
        lines += ["### What is needed to merge", ""]
        for rule in report.matched:
            todo = [
                req for r, req in blocking if r.id == rule.id and (req.effective != Status.PENDING or req.outcome.fix)
            ]
            if not todo:
                continue
            title = f"**`{rule.id}`**"
            if rule.description:
                title += f" · {rule.description}"
            lines += [title, ""]
            for req in todo:
                lines.append(f"- **{req.label}**: {req.outcome.fix or req.outcome.summary}")
                if req.outcome.status in (Status.FAIL, Status.ERROR):
                    lines += [f"  - {d}" for d in req.outcome.details[:3]]
                    if len(req.outcome.details) > 3:
                        lines.append(f"  - and {len(req.outcome.details) - 3} more")
            if rule.instructions:
                lines.append(f"  <sub>{rule.instructions.strip()}</sub>")
            lines.append("")
        template = report.evidence_template()
        if template:
            lines += [
                "<details><summary>Evidence template</summary>",
                "",
                "Paste into the PR description and fill in the placeholders.",
                "",
                evidence.render(template, report.evidence_block),
                "",
                "</details>",
                "",
            ]

    warnings = report.warnings()
    if warnings:
        lines += ["<details><summary>Warnings, not blocking</summary>", ""]
        for rule, req in warnings:
            note = f" {req.instructions.strip()}" if req.instructions else ""
            lines.append(f"- **{req.label}** (`{rule.id}`): {req.outcome.summary}.{note}")
        lines += ["", "</details>", ""]

    lines.append(
        f"<sub>Updated {report.evaluated_at}. Re-evaluated on push, label, comment and CI completion. "
        f"`mergeproof explain` shows the same requirements locally.</sub>"
    )
    return "\n".join(lines)


def explain_markdown(report: Report, policy: Policy, explanations: dict[tuple[str, str], str]) -> str:
    """What this change must prove and what is missing right now. Written for agents and people alike."""
    lines = [f"# What this change must prove ({report.verdict.value})", ""]
    if not report.matched:
        lines.append("No rules apply to the current diff.")
        return "\n".join(lines)
    for rule in report.matched:
        lines += [f"## {rule.id} [{rule.severity.value}]", ""]
        if rule.description:
            lines += [rule.description, ""]
        if rule.files:
            shown = ", ".join(f"`{f}`" for f in rule.files[:8])
            more = f" and {len(rule.files) - 8} more" if len(rule.files) > 8 else ""
            lines += [f"Triggered by {shown}{more}.", ""]
        for req in rule.requirements:
            lines.append(f"- {ICON[req.outcome.status]} **{req.label}**: {explanations.get((rule.id, req.label), '')}")
            lines.append(f"  - now: {req.outcome.summary}")
            lines += [f"  - {d}" for d in req.outcome.details[:6]]
            if req.outcome.fix and req.outcome.status not in (Status.PASS, Status.SKIP):
                lines.append(f"  - fix: {req.outcome.fix}")
            if req.instructions:
                lines.append(f"  - note: {req.instructions.strip()}")
        lines.append("")
    template = report.evidence_template()
    if template:
        lines += [
            "## Evidence block to add to the PR description",
            "",
            evidence.render(template, policy.evidence_block),
            "",
        ]
    return "\n".join(lines)
