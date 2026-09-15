from __future__ import annotations

from urllib.parse import quote

from mergeproof import evidence
from mergeproof.policy import Policy
from mergeproof.report import Report, RequirementResult, RuleResult, Status

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
PILL_COLOR = {
    Status.PASS: "2ea043",
    Status.SKIP: "6e7781",
    Status.WARN: "dbab09",
    Status.PENDING: "dbab09",
    Status.FAIL: "cf222e",
    Status.ERROR: "cf222e",
}
LABEL_COLOR = "1f2328"


def shield(label: str, value: str, color: str, logo: str | None = None, alt: str | None = None) -> str:
    """A shields.io badge as a Markdown image. Dashes and underscores are escaped the way shields expects."""

    def part(text: str) -> str:
        return quote(text.replace("-", "--").replace("_", "__"), safe="")

    url = f"https://img.shields.io/badge/{part(label)}-{part(value)}-{color}?style=flat-square&labelColor={LABEL_COLOR}"
    if logo:
        url += f"&logo={logo}"
    return f"![{alt or f'{label}: {value}'}]({url})"


def status_pill(status: Status) -> str:
    return shield("", WORD[status].strip("*"), PILL_COLOR[status], alt=WORD[status].strip("*")).replace(
        "badge/-", "badge/"
    )


def rule_pill(rule: RuleResult) -> str:
    """One pill per rule: `tool tests | 2 / 2` in the colour of its worst requirement."""
    statuses = [req.effective for req in rule.requirements]
    satisfied = sum(1 for st in statuses if st in (Status.PASS, Status.SKIP))
    if any(st in (Status.FAIL, Status.ERROR) for st in statuses):
        color, value = PILL_COLOR[Status.FAIL], f"{satisfied} / {len(statuses)}"
    elif Status.PENDING in statuses:
        color, value = PILL_COLOR[Status.PENDING], f"{satisfied} / {len(statuses)}"
    elif Status.WARN in statuses:
        color, value = PILL_COLOR[Status.WARN], "warn"
    else:
        color, value = PILL_COLOR[Status.PASS], f"{satisfied} / {len(statuses)}"
    return shield(rule.id.replace("-", " "), value, color)


def badge(report: Report) -> str:
    total = len(report.requirements)
    counts = report.counts()
    done = counts[Status.PASS] + counts[Status.SKIP]
    value = f"{done} / {total}" if total else "no rules apply"
    return shield("mergeproof", value, BADGE_COLOR[report.verdict], logo=BADGE_LOGO, alt=f"mergeproof: {value}")


def sentence(report: Report) -> str:
    total = len(report.requirements)
    counts = report.counts()
    done = counts[Status.PASS] + counts[Status.SKIP]
    where = ""
    if report.head_sha:
        repo_url = f"https://github.com/{report.repo}" if report.repo else PROJECT_URL
        where = f" for [`{report.head_sha[:7]}`]({repo_url}/commit/{report.head_sha})"
    if done == total:
        return f"**All {total} requirements satisfied**{where}."
    return f"**{done} of {total} requirements satisfied**{where}. To merge:"


def links(report: Report, run_url: str | None, receipt_url: str | None = None) -> str:
    items = []
    if report.repo and report.base_ref:
        items.append(f"[policy](https://github.com/{report.repo}/blob/{report.base_ref}/{report.policy_path})")
    if run_url:
        items.append(f"[details]({run_url})")
    if receipt_url:
        items.append(f"[receipt]({receipt_url})")
    items.append(f"[docs]({PROJECT_URL})")
    return " · ".join(items)


def what_to_do(req: RequirementResult) -> str:
    text = req.outcome.fix or req.outcome.summary
    extra = [d for d in req.outcome.details[:2]]
    if extra:
        text += " " + " ".join(f"<br><sub>{d}</sub>" for d in extra)
    return text


def requirement_rows(pairs: list[tuple[RuleResult, RequirementResult]]) -> list[str]:
    rows = ["| Status | Requirement | Detail |", "|:--|:--|:--|"]
    for rule, req in pairs:
        detail = req.outcome.summary
        if req.outcome.details:
            # 12, not 4: a reader asked to open before/after evidence should see
            # every pair, not be told "and 2 more" about the thing under review.
            shown = [d.replace("|", "\\|") for d in req.outcome.details[:12]]
            if len(req.outcome.details) > 12:
                shown.append(f"and {len(req.outcome.details) - 12} more")
            detail += "<br><sub>" + "<br>".join(shown) + "</sub>"
        rows.append(f"| {status_pill(req.effective)} | {req.label}<br><sub>{rule.id}</sub> | {detail} |")
    return rows


def report_markdown(
    report: Report, marker: bool = True, run_url: str | None = None, receipt_url: str | None = None
) -> str:
    """The sticky PR comment: a scorecard of rule pills, then only the work, then the rest folded."""
    lines: list[str] = [MARKER] if marker else []
    if not report.matched:
        tail = links(report, run_url, receipt_url)
        lines += [f"{badge(report)} &nbsp;No rules apply to this change. <sub>{tail}</sub>"]
        return "\n".join(lines)

    pills = " ".join([badge(report), *(rule_pill(rule) for rule in report.matched)])
    lines += [pills, "", sentence(report), ""]

    blocking = [
        (rule, req) for rule, req in report.blocking_unmet() if req.effective != Status.PENDING or req.outcome.fix
    ]
    rest = [(rule, req) for rule, req in report.requirements if (rule, req) not in blocking]
    if blocking:
        lines += ["| Needed | What to do |", "|:--|:--|"]
        for rule, req in blocking:
            lines.append(f"| {status_pill(req.effective)} {req.label}<br><sub>{rule.id}</sub> | {what_to_do(req)} |")
        lines.append("")
        instructions = {rule.id: rule.instructions for rule, _ in blocking if rule.instructions}
        for rule_id, text in instructions.items():
            lines.append(f"<sub>**{rule_id}**: {text.strip()}</sub>")
        if instructions:
            lines.append("")
        template = report.evidence_template()
        if template:
            lines += [
                "**Evidence template**, to paste into the PR description:",
                "",
                evidence.render(template, report.evidence_block),
                "",
            ]
        if rest:
            lines += ["**Everything else**", "", *requirement_rows(rest), ""]
    else:
        lines += [*requirement_rows(rest), ""]

    lines.append(
        f"<sub>Updated {report.evaluated_at} · re-evaluated on push, label, comment and CI completion · "
        f"`mergeproof explain` shows this locally · {links(report, run_url, receipt_url)}</sub>"
    )
    return "\n".join(lines)


def explain_markdown(report: Report, policy: Policy, explanations: dict[tuple[str, str], str]) -> str:
    """What this change must prove and what is missing right now. Written for agents and people alike."""
    lines = [f"# What this change must prove ({report.verdict.value})", ""]
    if not report.matched:
        lines.append("No rules apply to the current diff.")
        return "\n".join(lines)
    for rule in report.matched:
        origin = f" <sub>from {rule.source}</sub>" if rule.source else ""
        lines += [f"## {rule.id} [{rule.severity.value}]{origin}", ""]
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
