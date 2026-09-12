"""GitHub Actions workflow commands.

Printed to stdout inside a job, ``::error file=…`` lines become annotations on that job's own
check run, which is always the newest one on the commit. That is where file-level findings
belong; the commit status carries the verdict.
"""

from __future__ import annotations

from mergeproof.policy import Severity
from mergeproof.report import Report, Status


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape(text).replace(":", "%3A").replace(",", "%2C")


def workflow_commands(report: Report) -> list[str]:
    lines: list[str] = []
    for _, req in report.requirements:
        level = (
            "error"
            if req.severity == Severity.BLOCK and req.outcome.status in (Status.FAIL, Status.ERROR)
            else "warning"
        )
        for note in req.outcome.annotations:
            title = _escape_property("mergeproof: " + req.label)
            props = f"file={_escape_property(note.path)},line={note.line},title={title}"
            lines.append(f"::{level} {props}::{_escape(note.message)}")
    if report.verdict in (Status.FAIL, Status.PENDING):
        level = "error" if report.verdict == Status.FAIL else "warning"
        lines.append(f"::{level} title=mergeproof::{_escape(report.headline())}")
    return lines
