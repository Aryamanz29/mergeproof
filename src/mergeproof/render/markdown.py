from __future__ import annotations

from mergeproof import evidence
from mergeproof.policy import Policy, Severity
from mergeproof.report import UNMET, Report, RuleResult, Status

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


def meter(done: int, total: int, width: int = 10) -> str:
    if total == 0:
        return ""
    filled = round(width * done / total)
    return "`" + "▰" * filled + "▱" * (width - filled) + "`"


def rule_status(rule: RuleResult) -> Status:
    statuses = [req.outcome.status for req in rule.requirements]
    for status in (Status.ERROR, Status.FAIL, Status.PENDING, Status.WARN):
        if status in statuses:
            return status
    return Status.PASS


def report_markdown(report: Report, marker: bool = True) -> str:
    """The sticky PR comment.

    One headline with a progress meter, then one block per rule: rules with work left are
    expanded and say exactly what to do; satisfied rules are collapsed to a single line.
    """
    verdict = report.verdict
    lines: list[str] = [MARKER] if marker else []
    sha = f" · `{report.head_sha[:7]}`" if report.head_sha else ""
    if not report.matched:
        lines.append(f"✅ **mergeproof**: no rules apply to this change{sha}")
        return "\n".join(lines)

    counts = report.counts()
    total = len(report.requirements)
    done = counts[Status.PASS] + counts[Status.SKIP]
    rest = " · ".join(f"{n} {status.value}" for status, n in counts.items() if n and status in UNMET)
    lines += [
        f"## {ICON[verdict]} mergeproof: {HEADLINE.get(verdict, verdict.value)}",
        "",
        f"{meter(done, total)} **{done} of {total}** requirements satisfied" + (f" · {rest}" if rest else "") + sha,
        "",
    ]

    for rule in report.matched:
        status = rule_status(rule)
        satisfied = sum(1 for r in rule.requirements if r.outcome.status in (Status.PASS, Status.SKIP))
        open_attr = " open" if status in UNMET else ""
        title = f"{ICON[status]} <b>{rule.id}</b> · {satisfied} of {len(rule.requirements)}"
        if rule.description:
            title += f" <sub>{rule.description}</sub>"
        lines += [f"<details{open_attr}><summary>{title}</summary>", ""]
        lines += ["| | Requirement | Now |", "|:-:|---|---|"]
        for req in rule.requirements:
            note = "" if req.severity == Severity.BLOCK else " <sub>warn</sub>"
            lines.append(f"| {ICON[req.outcome.status]} | {req.label}{note} | {req.outcome.summary} |")
        todo = [req for req in rule.requirements if req.outcome.status in UNMET]
        if todo:
            lines += ["", "**To do**", ""]
            for req in todo:
                lines.append(f"- {ICON[req.outcome.status]} **{req.label}**: {req.outcome.fix or req.outcome.summary}")
                if req.outcome.status in (Status.FAIL, Status.ERROR):
                    lines += [f"  - {d}" for d in req.outcome.details[:3]]
                    if len(req.outcome.details) > 3:
                        lines.append(f"  - and {len(req.outcome.details) - 3} more")
                if req.instructions:
                    lines.append(f"  - {req.instructions.strip()}")
        lines += ["", "</details>", ""]

    template = report.evidence_template()
    if template:
        lines += [
            "<details><summary>📋 Evidence template · paste into the PR description and fill in</summary>",
            "",
            evidence.render(template, report.evidence_block),
            "",
            "</details>",
            "",
        ]
    lines.append(
        f"<sub>Evaluated {report.evaluated_at} · updates on push, label, comment and CI completion · "
        f"`mergeproof explain` shows this locally</sub>"
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
