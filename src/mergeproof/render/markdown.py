from __future__ import annotations

from mergeproof import evidence
from mergeproof.policy import Policy, Severity
from mergeproof.report import Report, Status

MARKER = "<!-- mergeproof-report -->"

ICON = {
    Status.PASS: "✅",
    Status.FAIL: "❌",
    Status.WARN: "⚠️",
    Status.PENDING: "⏳",
    Status.SKIP: "⏭️",
    Status.ERROR: "💥",
}

HEADLINE = {
    Status.PASS: "all evidence present",
    Status.FAIL: "evidence missing",
    Status.PENDING: "waiting for evidence",
    Status.WARN: "passing with warnings",
}


def report_markdown(report: Report, marker: bool = True) -> str:
    """The sticky PR comment."""
    verdict = report.verdict
    lines: list[str] = [MARKER] if marker else []
    title = f"## {ICON[verdict]} mergeproof: {HEADLINE.get(verdict, verdict.value)}"
    if report.head_sha:
        title += f" <sub>`{report.head_sha[:7]}`</sub>"
    lines += [title, ""]
    if not report.matched:
        lines.append("No rules apply to this change.")
        return "\n".join(lines)

    lines += ["| Rule | Requirement | | Detail |", "|---|---|:-:|---|"]
    for rule, req in report.requirements:
        note = "" if req.severity == Severity.BLOCK else " <sub>(warn)</sub>"
        lines.append(f"| `{rule.id}` | {req.label}{note} | {ICON[req.outcome.status]} | {req.outcome.summary} |")
    lines.append("")

    unmet = report.unmet()
    if unmet:
        lines += ["### Still needed", ""]
        for rule, req in unmet:
            lines.append(f"**{req.label}** (`{rule.id}`): {req.outcome.summary}")
            lines += [f"- {d}" for d in req.outcome.details[:8]]
            if req.outcome.fix:
                lines.append(f"- **Fix:** {req.outcome.fix}")
            if req.instructions:
                lines.append(f"- {req.instructions.strip()}")
            lines.append("")
        template = report.evidence_template()
        if template:
            lines += [
                "<details><summary>Evidence template: paste into the PR description and fill in</summary>",
                "",
                evidence.render(template, report.evidence_block),
                "",
                "</details>",
                "",
            ]
    lines.append(f"<sub>`mergeproof explain` shows these requirements locally · source: {report.source}</sub>")
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
