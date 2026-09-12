from __future__ import annotations

from mergeproof import evidence
from mergeproof.policy import Policy, Severity
from mergeproof.report import Report, RequirementResult, Status

MARKER = "<!-- mergeproof-report -->"
LOGO_URL = "https://raw.githubusercontent.com/Aryamanz29/mergeproof/main/docs/logo.png"
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


def effective(req: RequirementResult) -> Status:
    """A failing requirement on a warn-only rule is a warning, which is how the verdict treats it too."""
    status = req.outcome.status
    if req.severity == Severity.WARN and status in (Status.FAIL, Status.ERROR):
        return Status.WARN
    return status


def tally(report: Report) -> dict[Status, int]:
    counts = dict.fromkeys(Status, 0)
    for _, req in report.requirements:
        counts[effective(req)] += 1
    return counts


def badge(report: Report) -> str:
    total = len(report.requirements)
    counts = tally(report)
    done = counts[Status.PASS] + counts[Status.SKIP]
    label = f"{done}%2F{total}" if total else "no%20rules"
    return f"![evidence {done} of {total}](https://img.shields.io/badge/evidence-{label}-{BADGE_COLOR[report.verdict]}?style=flat-square)"


def sentence(report: Report) -> str:
    total = len(report.requirements)
    counts = tally(report)
    done = counts[Status.PASS] + counts[Status.SKIP]
    where = ""
    if report.head_sha:
        short = report.head_sha[:7]
        repo_url = f"https://github.com/{report.repo}" if report.repo else PROJECT_URL
        where = f" for [`{short}`]({repo_url}/commit/{report.head_sha})"
    if done == total:
        return f"**All {total} requirements are satisfied**{where}."
    parts = []
    if counts[Status.FAIL] + counts[Status.ERROR]:
        parts.append(f"{counts[Status.FAIL] + counts[Status.ERROR]} missing")
    if counts[Status.PENDING]:
        parts.append(f"{counts[Status.PENDING]} pending")
    if counts[Status.WARN]:
        parts.append(f"{counts[Status.WARN]} warning" + ("s" if counts[Status.WARN] > 1 else ""))
    return f"**{total - done} of {total} requirements need attention**{where}: {', '.join(parts)}."


def header(report: Report, run_url: str | None) -> str:
    links = []
    if report.repo and report.base_ref:
        links.append(f"[policy](https://github.com/{report.repo}/blob/{report.base_ref}/{report.policy_path})")
    if run_url:
        links.append(f"[details]({run_url})")
    links.append(f"[docs]({PROJECT_URL})")
    return (
        f'<img src="{LOGO_URL}" width="18" align="top" alt=""> **mergeproof** &nbsp;{badge(report)}'
        f" &nbsp;<sub>{' · '.join(links)}</sub>"
    )


def report_markdown(report: Report, marker: bool = True, run_url: str | None = None) -> str:
    """The sticky PR comment: a header, one sentence, one table, next steps only when needed."""
    lines: list[str] = [MARKER] if marker else []
    lines += [header(report, run_url), ""]
    if not report.matched:
        lines.append("No rules apply to this change.")
        return "\n".join(lines)

    lines += [sentence(report), "", "| Rule | Requirement | Status | Detail |", "|:--|:--|:--|:--|"]
    for rule in report.matched:
        for index, req in enumerate(rule.requirements):
            name = f"`{rule.id}`" if index == 0 else ""
            label = req.label + (" <sub>warn only</sub>" if req.severity != Severity.BLOCK else "")
            lines.append(f"| {name} | {label} | {WORD[effective(req)]} | {req.outcome.summary} |")
    lines.append("")

    actionable = [
        (rule, req) for rule, req in report.unmet() if req.outcome.status != Status.PENDING or req.outcome.fix
    ]
    if actionable:
        lines += ["**Next steps**", ""]
        seen_rules: set[str] = set()
        for step, (rule, req) in enumerate(actionable, 1):
            if rule.id not in seen_rules:
                seen_rules.add(rule.id)
                note = f" <sub>{rule.instructions.strip()}</sub>" if rule.instructions else ""
                lines.append(f"`{rule.id}`{note}")
            lines.append(f"{step}. **{req.label}**: {req.outcome.fix or req.outcome.summary}")
            if req.outcome.status in (Status.FAIL, Status.ERROR):
                lines += [f"   - {d}" for d in req.outcome.details[:3]]
                if len(req.outcome.details) > 3:
                    lines.append(f"   - and {len(req.outcome.details) - 3} more")
            if req.instructions and req.instructions != rule.instructions:
                lines.append(f"   <br><sub>{req.instructions.strip()}</sub>")
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
