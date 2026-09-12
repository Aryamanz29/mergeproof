"""reviewdog diagnostic format, for inline review comments on the files concerned.

mergeproof report report.json -f rdjson | reviewdog -f=rdjson -reporter=github-pr-review
"""

from __future__ import annotations

import json

from mergeproof.policy import Severity
from mergeproof.report import Report


def rdjson(report: Report) -> str:
    diagnostics = []
    for rule, req in report.requirements:
        for note in req.outcome.annotations:
            diagnostics.append(
                {
                    "message": f"{req.label}: {note.message}",
                    "location": {"path": note.path, "range": {"start": {"line": note.line, "column": 1}}},
                    "severity": "ERROR" if req.severity == Severity.BLOCK else "WARNING",
                    "code": {"value": rule.id},
                }
            )
    return json.dumps(
        {
            "source": {"name": "mergeproof", "url": "https://github.com/Aryamanz29/mergeproof"},
            "severity": "ERROR" if report.verdict.value == "fail" else "WARNING",
            "diagnostics": diagnostics,
        },
        indent=2,
    )
