from __future__ import annotations

from mergeproof import evidence
from mergeproof.report import Report, Status

TAG = {
    Status.PASS: "ok  ",
    Status.FAIL: "FAIL",
    Status.WARN: "warn",
    Status.PENDING: "wait",
    Status.SKIP: "skip",
    Status.ERROR: "ERR ",
}


def report_text(report: Report, verbose: bool = False) -> str:
    """Plain text for terminals and logs. Unmet requirements always show their details."""
    requirements = report.requirements
    counts = {status: sum(1 for _, r in requirements if r.outcome.status == status) for status in Status}
    summary = ", ".join(f"{n} {s.value}" for s, n in counts.items() if n)
    lines = [
        f"mergeproof: {report.verdict.value.upper()}  ({len(report.matched)} rule(s), {summary or 'nothing to check'})"
    ]
    for rule in report.matched:
        lines.append(f"  {rule.id}")
        for req in rule.requirements:
            status = req.outcome.status
            note = " (warn)" if req.severity.value == "warn" else ""
            lines.append(f"    {TAG[status]}  {req.label}{note}: {req.outcome.summary}")
            if verbose or status not in (Status.PASS, Status.SKIP):
                for detail in req.outcome.details[:8]:
                    lines.append(f"          - {detail}")
                if req.outcome.fix and status not in (Status.PASS, Status.SKIP):
                    lines.append(f"          fix: {req.outcome.fix}")
    template = report.evidence_template()
    if template:
        lines += ["", "evidence block to add to the PR description:", evidence.render(template, report.evidence_block)]
    return "\n".join(lines)
